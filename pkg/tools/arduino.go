package tools

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

// ArduinoTool provides sketch compilation and upload via arduino-cli.
type ArduinoTool struct {
	fqbn     string // fully qualified board name, e.g. "arduino:zephyr:unoq"
	port     string // upload target, e.g. "192.168.1.42" or "/dev/ttyACM0"
	protocol string // upload protocol, e.g. "network" or "serial"
	timeout  time.Duration
}

// NewArduinoTool creates an ArduinoTool with board defaults.
func NewArduinoTool(fqbn, port, protocol string) *ArduinoTool {
	if fqbn == "" {
		fqbn = "arduino:zephyr:unoq"
	}
	return &ArduinoTool{
		fqbn:     fqbn,
		port:     port,
		protocol: protocol,
		timeout:  120 * time.Second,
	}
}

func (t *ArduinoTool) Name() string { return "arduino" }

func (t *ArduinoTool) Description() string {
	return "Compile and upload Arduino sketches using arduino-cli. " +
		"Actions: compile (compile a sketch and report errors), " +
		"upload (compile then upload to the connected board), " +
		"detect (list connected boards). " +
		"Provide the complete sketch source code in the 'sketch' parameter."
}

func (t *ArduinoTool) Parameters() map[string]any {
	return map[string]any{
		"type": "object",
		"properties": map[string]any{
			"action": map[string]any{
				"type":        "string",
				"enum":        []string{"compile", "upload", "detect"},
				"description": "Action to perform: compile (verify the sketch compiles), upload (compile and upload to board), detect (list connected boards)",
			},
			"sketch": map[string]any{
				"type":        "string",
				"description": "Complete Arduino sketch source code (.ino content). Required for compile and upload actions.",
			},
			"fqbn": map[string]any{
				"type":        "string",
				"description": "Fully qualified board name (e.g. arduino:zephyr:unoq). Optional — defaults to the configured board.",
			},
			"port": map[string]any{
				"type":        "string",
				"description": "Upload port (IP address or serial device path). Optional — defaults to the configured port.",
			},
		},
		"required": []string{"action"},
	}
}

func (t *ArduinoTool) Execute(ctx context.Context, args map[string]any) *ToolResult {
	if runtime.GOOS != "linux" {
		return ErrorResult("Arduino tool is only supported on Linux (Arduino Uno Q runs Debian).")
	}

	action, ok := args["action"].(string)
	if !ok {
		return ErrorResult("action is required")
	}

	switch action {
	case "compile":
		return t.compile(ctx, args, false)
	case "upload":
		return t.compile(ctx, args, true)
	case "detect":
		return t.detect(ctx)
	default:
		return ErrorResult(fmt.Sprintf("unknown action: %s (use compile, upload, or detect)", action))
	}
}

func (t *ArduinoTool) compile(ctx context.Context, args map[string]any, upload bool) *ToolResult {
	sketch, ok := args["sketch"].(string)
	if !ok || strings.TrimSpace(sketch) == "" {
		return ErrorResult("sketch is required — provide the complete .ino source code")
	}

	fqbn := t.fqbn
	if v, ok := args["fqbn"].(string); ok && v != "" {
		fqbn = v
	}

	port := t.port
	if v, ok := args["port"].(string); ok && v != "" {
		port = v
	}

	// Write sketch to a temp directory structured as arduino-cli expects:
	// <dir>/<dir>.ino
	tmpDir, err := os.MkdirTemp("", "qclaw-sketch-*")
	if err != nil {
		return ErrorResult(fmt.Sprintf("failed to create temp directory: %v", err))
	}
	defer os.RemoveAll(tmpDir)

	sketchName := filepath.Base(tmpDir)
	inoPath := filepath.Join(tmpDir, sketchName+".ino")

	if err := os.WriteFile(inoPath, []byte(sketch), 0o644); err != nil {
		return ErrorResult(fmt.Sprintf("failed to write sketch: %v", err))
	}

	// When running on the Uno Q itself, prefer OpenOCD + linuxgpiod
	// (no network credentials needed) over `arduino-cli --upload
	// --protocol network` (which uses SSH and would prompt for a
	// password in non-interactive mode and fail).
	//
	// Path: compile with --export-binaries to produce the .elf-zsk.bin,
	// then invoke openocd directly with the canonical sketch partition
	// address (0x8100000). See runFlashCommand for the address details.
	useLocalFlash := upload && fileExists("/opt/openocd/bin/openocd")

	cliArgs := []string{"compile", "--fqbn", fqbn}

	if useLocalFlash {
		cliArgs = append(cliArgs, "--export-binaries")
	} else if upload {
		cliArgs = append(cliArgs, "--upload")
		if port != "" {
			cliArgs = append(cliArgs, "--port", port)
		}
		if t.protocol != "" {
			cliArgs = append(cliArgs, "--protocol", t.protocol)
		}
	}

	cliArgs = append(cliArgs, tmpDir)

	compileResult := t.runCLI(ctx, cliArgs, upload && !useLocalFlash)
	if !useLocalFlash || compileResult.IsError {
		return compileResult
	}

	// Local-flash path: locate the .elf-zsk.bin produced by --export-binaries
	// and pipe it through `arduino-flash`. The binary path follows the
	// arduino-cli convention `<sketch>/build/<fqbn-with-dots>/<sketch>.ino.elf-zsk.bin`.
	fqbnDir := strings.ReplaceAll(fqbn, ":", ".")
	binPath := filepath.Join(tmpDir, "build", fqbnDir, sketchName+".ino.elf-zsk.bin")
	if !fileExists(binPath) {
		return ErrorResult(fmt.Sprintf(
			"compile succeeded but expected output binary not found at %s\nCompile output:\n%s",
			binPath, compileResult.ForLLM,
		))
	}

	flashResult := t.runFlashCommand(ctx, binPath)
	if flashResult.IsError {
		return flashResult
	}
	return NewToolResult(fmt.Sprintf(
		"Sketch compiled and flashed to the board.\n\n--- compile ---\n%s\n\n--- flash ---\n%s",
		compileResult.ForLLM, flashResult.ForLLM,
	))
}

// runFlashCommand flashes the compiled sketch to the Uno Q's STM32U585
// using OpenOCD + linuxgpiod from the Linux side — no SSH, no network creds.
//
// The pre-installed /usr/local/bin/arduino-flash wrapper has a bug: its
// hardcoded address is 0x80F0000, but the correct sketch partition (per
// boards.txt: unoq.upload.address) is 0x8100000. Sketches written to
// 0x80F0000 land in a reserved area near the end of bank 1 and never run.
//
// This implementation invokes openocd directly with the canonical address
// from the zephyr core's flash_sketch.cfg.
func (t *ArduinoTool) runFlashCommand(ctx context.Context, binPath string) *ToolResult {
	cmdCtx, cancel := context.WithTimeout(ctx, t.timeout)
	defer cancel()

	const (
		openocd       = "/opt/openocd/bin/openocd"
		openocdShare  = "/opt/openocd"
		gpiodCfg      = "openocd_gpiod.cfg"
		sketchAddress = "0x8100000"
	)

	flashCmds := fmt.Sprintf(
		"reset_config srst_only srst_nogate srst_push_pull connect_assert_srst; "+
			"init; reset; halt; flash info 0; "+
			"flash write_image erase %s %s bin; "+
			"reset run; shutdown",
		binPath, sketchAddress,
	)

	cmd := exec.CommandContext(cmdCtx, openocd,
		"-d2",
		"-s", openocdShare,
		"-f", gpiodCfg,
		"-c", flashCmds,
	)

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	output := stdout.String()
	if stderr.Len() > 0 {
		if output != "" {
			output += "\n"
		}
		output += stderr.String()
	}
	if err != nil {
		if cmdCtx.Err() == context.DeadlineExceeded {
			return ErrorResult(fmt.Sprintf("openocd flash timed out after %v", t.timeout))
		}
		return ErrorResult(fmt.Sprintf("Flash failed:\n%s", output))
	}
	return NewToolResult(output)
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func (t *ArduinoTool) detect(ctx context.Context) *ToolResult {
	return t.runCLI(ctx, []string{"board", "list"}, false)
}

func (t *ArduinoTool) runCLI(ctx context.Context, cliArgs []string, isUpload bool) *ToolResult {
	cmdCtx, cancel := context.WithTimeout(ctx, t.timeout)
	defer cancel()

	cmd := exec.CommandContext(cmdCtx, "arduino-cli", cliArgs...)

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err := cmd.Run()

	output := stdout.String()
	if stderr.Len() > 0 {
		if output != "" {
			output += "\n"
		}
		output += stderr.String()
	}

	if err != nil {
		if cmdCtx.Err() == context.DeadlineExceeded {
			return ErrorResult(fmt.Sprintf("arduino-cli timed out after %v", t.timeout))
		}

		// Compilation errors are the most useful output — return them clearly
		action := "Compilation"
		if isUpload {
			action = "Upload"
		}
		return ErrorResult(fmt.Sprintf("%s failed:\n%s", action, output))
	}

	if isUpload {
		return NewToolResult(fmt.Sprintf("Sketch compiled and uploaded successfully.\n%s", output))
	}
	return NewToolResult(fmt.Sprintf("Sketch compiled successfully (no errors).\n%s", output))
}
