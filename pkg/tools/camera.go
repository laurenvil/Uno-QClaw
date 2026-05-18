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

// CameraTool captures a still frame from a V4L2 video device using GStreamer.
//
// Narrowly scoped on purpose: this is NOT an exec wrapper — it builds a fixed
// GStreamer pipeline shape that captures num-buffers=1 from a v4l2src and
// writes to a JPEG file. The LLM can choose the device, resolution, and
// output path, but cannot inject arbitrary GStreamer plumbing or shell.
//
// Linux-only. On other platforms Execute returns ErrorResult.
type CameraTool struct {
	defaultDevice string
	defaultWidth  int
	defaultHeight int
	timeout       time.Duration
}

func NewCameraTool() *CameraTool {
	return &CameraTool{
		defaultDevice: "/dev/video0",
		defaultWidth:  1280,
		defaultHeight: 720,
		timeout:       30 * time.Second,
	}
}

func (t *CameraTool) Name() string { return "camera" }

func (t *CameraTool) Description() string {
	return "Capture a single still image from a Uno Q camera (MIPI-CSI-2 on JMEDIA, or a " +
		"USB webcam in SBC mode). Uses GStreamer's v4l2src under the hood and writes a JPEG " +
		"to disk. Returns the absolute path of the saved image. Linux-only. Requires " +
		"gst-launch-1.0 and the camera to be enumerated under /dev/video*."
}

func (t *CameraTool) Parameters() map[string]any {
	return map[string]any{
		"type": "object",
		"properties": map[string]any{
			"device": map[string]any{
				"type": "string",
				"description": "V4L2 device path, e.g. /dev/video0. Optional — defaults to " +
					"/dev/video0. Run `v4l2-ctl --list-devices` on the board to enumerate.",
			},
			"width": map[string]any{
				"type":        "integer",
				"description": "Capture width in pixels. Optional — defaults to 1280.",
			},
			"height": map[string]any{
				"type":        "integer",
				"description": "Capture height in pixels. Optional — defaults to 720.",
			},
			"output": map[string]any{
				"type": "string",
				"description": "Output JPEG path. Optional — defaults to a unique file under " +
					"/tmp/. Path is sanitised: only filenames under /tmp/ or the user's home " +
					"directory are accepted.",
			},
		},
		"required": []string{},
	}
}

// allowedOutputDir reports whether the destination path is under one of the
// directories QClaw considers safe to write image captures into. Refuses
// absolute paths into /etc, /usr, /var, etc.
func allowedOutputDir(p string) bool {
	clean := filepath.Clean(p)
	if !filepath.IsAbs(clean) {
		return false
	}
	allowed := []string{"/tmp/", "/var/tmp/"}
	if home, err := os.UserHomeDir(); err == nil {
		allowed = append(allowed, home+string(os.PathSeparator))
	}
	for _, prefix := range allowed {
		if strings.HasPrefix(clean, prefix) {
			return true
		}
	}
	return false
}

func (t *CameraTool) Execute(ctx context.Context, args map[string]any) *ToolResult {
	if runtime.GOOS != "linux" {
		return ErrorResult("camera tool is only supported on Linux (Arduino Uno Q runs Debian).")
	}

	device := t.defaultDevice
	if v, ok := args["device"].(string); ok && v != "" {
		device = v
	}
	// Light validation: must be /dev/video<n>
	if !strings.HasPrefix(device, "/dev/video") {
		return ErrorResult("device must be a /dev/video* path")
	}
	if _, err := os.Stat(device); err != nil {
		return ErrorResult(fmt.Sprintf("device %s not present: %v", device, err))
	}

	width := t.defaultWidth
	if v, ok := args["width"].(float64); ok && v > 0 && v <= 4096 {
		width = int(v)
	} else if v, ok := args["width"].(int); ok && v > 0 && v <= 4096 {
		width = v
	}
	height := t.defaultHeight
	if v, ok := args["height"].(float64); ok && v > 0 && v <= 4096 {
		height = int(v)
	} else if v, ok := args["height"].(int); ok && v > 0 && v <= 4096 {
		height = v
	}

	var output string
	if v, ok := args["output"].(string); ok && v != "" {
		if !allowedOutputDir(v) {
			return ErrorResult(
				"output path must be absolute and under /tmp/, /var/tmp/, or the user's home directory")
		}
		output = filepath.Clean(v)
	} else {
		f, err := os.CreateTemp("", "qclaw-camera-*.jpg")
		if err != nil {
			return ErrorResult(fmt.Sprintf("failed to allocate output file: %v", err))
		}
		output = f.Name()
		_ = f.Close()
	}

	if _, err := exec.LookPath("gst-launch-1.0"); err != nil {
		return ErrorResult(
			"gst-launch-1.0 not found on PATH. Install: sudo apt install gstreamer1.0-tools " +
				"gstreamer1.0-plugins-good")
	}

	cmdCtx, cancel := context.WithTimeout(ctx, t.timeout)
	defer cancel()

	pipeline := []string{
		"v4l2src", "device=" + device, "num-buffers=1",
		"!", fmt.Sprintf("video/x-raw,width=%d,height=%d", width, height),
		"!", "videoconvert",
		"!", "jpegenc",
		"!", "filesink", "location=" + output,
	}

	cmd := exec.CommandContext(cmdCtx, "gst-launch-1.0", pipeline...)
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
			return ErrorResult(fmt.Sprintf("camera capture timed out after %v", t.timeout))
		}
		return ErrorResult(fmt.Sprintf("camera capture failed:\n%s", combined))
	}

	info, statErr := os.Stat(output)
	if statErr != nil {
		return ErrorResult(fmt.Sprintf("capture reported success but file missing: %s", output))
	}
	if info.Size() == 0 {
		return ErrorResult(fmt.Sprintf("capture produced an empty file at %s", output))
	}

	return NewToolResult(fmt.Sprintf(
		"Captured %d×%d frame from %s.\nSaved to: %s (%d bytes).\nView with: feh %s "+
			"  OR  scp it to a host with an image viewer.",
		width, height, device, output, info.Size(), output,
	))
}
