package tools

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"
)

// I2CDetectTool wraps `i2cdetect -y -r <bus>` to enumerate I²C devices on a
// Linux i2c bus. Read-only: it only scans, it does not write to any device.
//
// Narrowly scoped: only `list` (enumerate buses) and `scan` (run i2cdetect on
// one bus) actions. No arbitrary i2cset/i2cget — those would need a separate
// tool with a separate threat model.
type I2CDetectTool struct {
	timeout time.Duration
}

func NewI2CDetectTool() *I2CDetectTool {
	return &I2CDetectTool{timeout: 10 * time.Second}
}

func (t *I2CDetectTool) Name() string { return "i2cdetect" }

func (t *I2CDetectTool) Description() string {
	return "Enumerate Linux I²C buses and scan for connected devices. Actions: list (show all " +
		"/dev/i2c-* buses) and scan (run `i2cdetect -y -r <bus>` and report which addresses " +
		"responded). Read-only — does not modify any device state. Requires the i2c-tools " +
		"package (`sudo apt install i2c-tools`) and read access to /dev/i2c-*."
}

func (t *I2CDetectTool) Parameters() map[string]any {
	return map[string]any{
		"type": "object",
		"properties": map[string]any{
			"action": map[string]any{
				"type":        "string",
				"enum":        []string{"list", "scan"},
				"description": "list = enumerate /dev/i2c-* buses; scan = run i2cdetect on one bus.",
			},
			"bus": map[string]any{
				"type":        "integer",
				"description": "Bus number for scan action (e.g. 0 for /dev/i2c-0). Run 'list' first to discover what's available.",
			},
		},
		"required": []string{"action"},
	}
}

func (t *I2CDetectTool) Execute(ctx context.Context, args map[string]any) *ToolResult {
	if runtime.GOOS != "linux" {
		return ErrorResult("i2cdetect tool is only supported on Linux (Arduino Uno Q runs Debian).")
	}
	action, ok := args["action"].(string)
	if !ok {
		return ErrorResult("action is required (list, scan)")
	}
	switch action {
	case "list":
		return t.list()
	case "scan":
		return t.scan(ctx, args)
	default:
		return ErrorResult(fmt.Sprintf("unknown action: %s (use list or scan)", action))
	}
}

func (t *I2CDetectTool) list() *ToolResult {
	matches, err := filepath.Glob("/dev/i2c-*")
	if err != nil {
		return ErrorResult(fmt.Sprintf("glob /dev/i2c-*: %v", err))
	}
	if len(matches) == 0 {
		return NewToolResult(
			"No /dev/i2c-* devices found. The MPU I²C buses may not be enabled in the device tree, " +
				"or the i2c-dev kernel module is not loaded (`sudo modprobe i2c-dev`).")
	}
	var out strings.Builder
	out.WriteString("Linux I²C buses (MPU side, 1.8 V domain on JMISC/JMEDIA):\n")
	for _, m := range matches {
		// Try to read the corresponding /sys/class/i2c-adapter for the bus name
		base := filepath.Base(m)
		name := ""
		sysName := filepath.Join("/sys/class/i2c-dev", base, "name")
		if data, err := os.ReadFile(sysName); err == nil {
			name = strings.TrimSpace(string(data))
		}
		if name != "" {
			out.WriteString(fmt.Sprintf("  %s   %s\n", m, name))
		} else {
			out.WriteString(fmt.Sprintf("  %s\n", m))
		}
	}
	out.WriteString("\nNote: The Arduino headers (D20/D21 = I²C2, A4/A5 = I²C3, Qwiic = I²C4) are MCU-side " +
		"and NOT visible here. Those are accessed from sketches via Wire/Wire1/Modulino, not from Linux.\n")
	return NewToolResult(out.String())
}

func (t *I2CDetectTool) scan(ctx context.Context, args map[string]any) *ToolResult {
	var bus int
	switch v := args["bus"].(type) {
	case float64:
		bus = int(v)
	case int:
		bus = v
	case string:
		n, err := strconv.Atoi(v)
		if err != nil {
			return ErrorResult(fmt.Sprintf("bus must be an integer, got %q", v))
		}
		bus = n
	default:
		return ErrorResult("bus is required for scan action (integer)")
	}
	if bus < 0 || bus > 99 {
		return ErrorResult(fmt.Sprintf("bus out of range: %d", bus))
	}
	devPath := fmt.Sprintf("/dev/i2c-%d", bus)
	if _, err := os.Stat(devPath); err != nil {
		return ErrorResult(fmt.Sprintf("%s does not exist: %v", devPath, err))
	}

	if _, err := exec.LookPath("i2cdetect"); err != nil {
		return ErrorResult(
			"i2cdetect not found on PATH. Install: sudo apt install i2c-tools")
	}

	cmdCtx, cancel := context.WithTimeout(ctx, t.timeout)
	defer cancel()

	// -y = non-interactive (no confirmation prompt)
	// -r = "smbus read byte" scan, safer than the default write probe
	cmd := exec.CommandContext(cmdCtx, "i2cdetect", "-y", "-r", strconv.Itoa(bus))
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	combined := stdout.String()
	if stderr.Len() > 0 {
		if combined != "" {
			combined += "\n"
		}
		combined += stderr.String()
	}
	if err != nil {
		if cmdCtx.Err() == context.DeadlineExceeded {
			return ErrorResult(fmt.Sprintf("i2cdetect timed out after %v", t.timeout))
		}
		return ErrorResult(fmt.Sprintf("i2cdetect failed:\n%s", combined))
	}
	return NewToolResult(fmt.Sprintf("Scan of %s:\n%s", devPath, combined))
}
