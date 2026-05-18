package tools

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
)

// SysfsLEDTool drives the MPU-side LEDs on the Uno Q through the Linux LED
// class at /sys/class/leds/<name>/brightness.
//
// Narrowly scoped: the action enum is set/list/trigger, and the led name is
// validated against the actual sysfs entries — the tool cannot be tricked into
// writing arbitrary paths.
//
// Active-low note: the Uno Q's RGB LEDs are active-low. The tool exposes a
// `brightness` value 0..255 in the natural "0 = off, 255 = fully on" sense
// and inverts internally before writing to sysfs. The user-facing skill
// documentation explains the inversion.
type SysfsLEDTool struct {
	root string
}

func NewSysfsLEDTool() *SysfsLEDTool {
	return &SysfsLEDTool{root: "/sys/class/leds"}
}

func (t *SysfsLEDTool) Name() string { return "sysfs_led" }

func (t *SysfsLEDTool) Description() string {
	return "Control the MPU-side RGB LEDs on the Uno Q via the Linux LED class (/sys/class/leds). " +
		"Actions: list (enumerate available LED names), set (set brightness 0–255 for one LED, " +
		"natural mapping: 0 = off, 255 = fully on; the active-low inversion is handled internally), " +
		"trigger (set a kernel trigger like 'heartbeat', 'none', 'disk-activity'). Linux-only. " +
		"Requires write access to /sys/class/leds/*/brightness (root or gpio-group membership)."
}

func (t *SysfsLEDTool) Parameters() map[string]any {
	return map[string]any{
		"type": "object",
		"properties": map[string]any{
			"action": map[string]any{
				"type":        "string",
				"enum":        []string{"list", "set", "trigger"},
				"description": "list = enumerate LED names; set = set brightness; trigger = set a kernel trigger mode.",
			},
			"led": map[string]any{
				"type": "string",
				"description": "LED name as it appears under /sys/class/leds (e.g. 'red:user', 'green:user', " +
					"'blue:user'). Required for set and trigger actions.",
			},
			"brightness": map[string]any{
				"type":        "integer",
				"description": "Brightness 0–255 (natural sense: 0 = off, 255 = fully on). Required for set action.",
			},
			"trigger_mode": map[string]any{
				"type": "string",
				"description": "Kernel trigger mode (e.g. 'none', 'heartbeat', 'disk-activity', 'timer'). " +
					"Run with action=list first to see which triggers each LED supports. Required for trigger action.",
			},
		},
		"required": []string{"action"},
	}
}

func (t *SysfsLEDTool) Execute(ctx context.Context, args map[string]any) *ToolResult {
	if runtime.GOOS != "linux" {
		return ErrorResult("sysfs_led is only supported on Linux (Arduino Uno Q runs Debian).")
	}

	action, ok := args["action"].(string)
	if !ok {
		return ErrorResult("action is required (list, set, trigger)")
	}

	switch action {
	case "list":
		return t.list()
	case "set":
		return t.set(args)
	case "trigger":
		return t.setTrigger(args)
	default:
		return ErrorResult(fmt.Sprintf("unknown action: %s (use list, set, or trigger)", action))
	}
}

func (t *SysfsLEDTool) list() *ToolResult {
	entries, err := os.ReadDir(t.root)
	if err != nil {
		return ErrorResult(fmt.Sprintf("cannot read %s: %v", t.root, err))
	}
	var out strings.Builder
	out.WriteString("Available LEDs under /sys/class/leds:\n")
	for _, e := range entries {
		name := e.Name()
		if name == "." || name == ".." {
			continue
		}
		// Try to read the current trigger to give the LLM more context
		trigPath := filepath.Join(t.root, name, "trigger")
		trig := ""
		if data, err := os.ReadFile(trigPath); err == nil {
			trig = strings.TrimSpace(string(data))
		}
		if trig != "" {
			out.WriteString(fmt.Sprintf("  - %s    [triggers: %s]\n", name, trig))
		} else {
			out.WriteString(fmt.Sprintf("  - %s\n", name))
		}
	}
	return NewToolResult(out.String())
}

// validateLEDName ensures the led arg names a real directory under /sys/class/leds.
// Rejects path traversal and anything that isn't a known LED.
func (t *SysfsLEDTool) validateLEDName(name string) (string, error) {
	if name == "" {
		return "", fmt.Errorf("led is required")
	}
	// LED names are like "red:user" or "blue:bt" — no slashes, no ".."
	if strings.ContainsAny(name, "/\\") || strings.Contains(name, "..") {
		return "", fmt.Errorf("invalid led name: %q", name)
	}
	dir := filepath.Join(t.root, name)
	if info, err := os.Stat(dir); err != nil || !info.IsDir() {
		return "", fmt.Errorf("led %q not found under %s", name, t.root)
	}
	return dir, nil
}

func (t *SysfsLEDTool) set(args map[string]any) *ToolResult {
	ledName, _ := args["led"].(string)
	dir, err := t.validateLEDName(ledName)
	if err != nil {
		return ErrorResult(err.Error())
	}

	var brightness int
	switch v := args["brightness"].(type) {
	case float64:
		brightness = int(v)
	case int:
		brightness = v
	case string:
		n, err := strconv.Atoi(v)
		if err != nil {
			return ErrorResult(fmt.Sprintf("brightness must be an integer 0..255, got %q", v))
		}
		brightness = n
	default:
		return ErrorResult("brightness is required (integer 0..255)")
	}
	if brightness < 0 || brightness > 255 {
		return ErrorResult(fmt.Sprintf("brightness out of range: %d (0..255)", brightness))
	}

	// Read max_brightness so we scale correctly; some LEDs accept 0..1 only.
	maxVal := 255
	if data, err := os.ReadFile(filepath.Join(dir, "max_brightness")); err == nil {
		if n, err := strconv.Atoi(strings.TrimSpace(string(data))); err == nil && n > 0 {
			maxVal = n
		}
	}

	// Active-low inversion: brightness=0 (user-facing "off") should write
	// max_brightness; brightness=255 (user-facing "on") should write 0.
	// Scale to the actual max_brightness.
	scaled := brightness * maxVal / 255
	inverted := maxVal - scaled

	path := filepath.Join(dir, "brightness")
	if err := os.WriteFile(path, []byte(strconv.Itoa(inverted)), 0o644); err != nil {
		return ErrorResult(fmt.Sprintf("failed to write %s: %v", path, err))
	}
	return NewToolResult(fmt.Sprintf(
		"Set %s brightness to %d/255 (scaled to %d/%d after active-low inversion).",
		ledName, brightness, inverted, maxVal,
	))
}

func (t *SysfsLEDTool) setTrigger(args map[string]any) *ToolResult {
	ledName, _ := args["led"].(string)
	dir, err := t.validateLEDName(ledName)
	if err != nil {
		return ErrorResult(err.Error())
	}
	mode, _ := args["trigger_mode"].(string)
	if mode == "" {
		return ErrorResult("trigger_mode is required (e.g. 'none', 'heartbeat', 'disk-activity')")
	}
	// Validate against the kernel's published list to give a friendly error
	if data, err := os.ReadFile(filepath.Join(dir, "trigger")); err == nil {
		available := string(data)
		// The kernel lists triggers space-separated, with the active one in [brackets]
		clean := strings.ReplaceAll(strings.ReplaceAll(available, "[", ""), "]", "")
		known := strings.Fields(clean)
		ok := false
		for _, k := range known {
			if k == mode {
				ok = true
				break
			}
		}
		if !ok {
			return ErrorResult(fmt.Sprintf(
				"trigger_mode %q not supported for %s. Available: %s",
				mode, ledName, strings.TrimSpace(clean),
			))
		}
	}
	path := filepath.Join(dir, "trigger")
	if err := os.WriteFile(path, []byte(mode), 0o644); err != nil {
		return ErrorResult(fmt.Sprintf("failed to write trigger: %v", err))
	}
	return NewToolResult(fmt.Sprintf("Set %s trigger to %q.", ledName, mode))
}
