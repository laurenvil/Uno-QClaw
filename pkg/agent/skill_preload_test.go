package agent

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// writeSkill writes a SKILL.md and a set of reference files under
// workspace/skills/<name>/. Returns nothing — t.Fatalf on error so failure
// fails the test immediately rather than producing confusing downstream nil
// matches.
func writeSkill(t *testing.T, workspace, name, skillBody string, refs map[string]string) {
	t.Helper()
	skillDir := filepath.Join(workspace, "skills", name)
	if err := os.MkdirAll(filepath.Join(skillDir, "references"), 0o755); err != nil {
		t.Fatalf("mkdir skill dir: %v", err)
	}
	frontmatter := "---\nname: " + name + "\ndescription: test description for " + name + "\n---\n\n"
	if err := os.WriteFile(filepath.Join(skillDir, "SKILL.md"), []byte(frontmatter+skillBody), 0o644); err != nil {
		t.Fatalf("write SKILL.md: %v", err)
	}
	for refName, body := range refs {
		if err := os.WriteFile(filepath.Join(skillDir, "references", refName), []byte(body), 0o644); err != nil {
			t.Fatalf("write %s: %v", refName, err)
		}
	}
}

// setupPreloadTest builds a ContextBuilder pointing at a fresh tmp workspace
// that holds the two QClaw skills with sentinel bodies so we can grep for them
// in the preload output.
func setupPreloadTest(t *testing.T) *ContextBuilder {
	t.Helper()
	ws := t.TempDir()

	writeSkill(t, ws, "sketch-patterns", "SKETCH_INDEX_BODY",
		map[string]string{
			"breathing.md":     "REF_BREATHING_BODY",
			"blink.md":         "REF_BLINK_BODY",
			"button.md":        "REF_BUTTON_BODY",
			"potentiometer.md": "REF_POT_BODY",
			"servo.md":         "REF_SERVO_BODY",
			"upload.md":        "REF_UPLOAD_BODY",
			"can.md":           "REF_CAN_BODY",
			"dac.md":           "REF_DAC_BODY",
			"opamp.md":         "REF_OPAMP_BODY",
		},
	)
	writeSkill(t, ws, "modulino", "MODULINO_INDEX_BODY", nil)
	writeSkill(t, ws, "linux-led", "LINUXLED_INDEX_BODY", nil)
	writeSkill(t, ws, "led-matrix", "LEDMATRIX_INDEX_BODY",
		map[string]string{
			"scroll-text.md": "REF_SCROLLTEXT_BODY",
		},
	)
	writeSkill(t, ws, "uno-q-hardware", "HARDWARE_INDEX_BODY",
		map[string]string{
			"pinout.md":         "REF_PINOUT_BODY",
			"voltage-safety.md": "REF_VOLTAGE_BODY",
			"connectors.md":     "REF_CONNECTORS_BODY",
			"power.md":          "REF_POWER_BODY",
		},
	)
	writeSkill(t, ws, "bridge", "BRIDGE_INDEX_BODY",
		map[string]string{
			"python-side.md": "REF_BRIDGE_PYTHON_BODY",
			"mcu-side.md":    "REF_BRIDGE_MCU_BODY",
			"examples.md":    "REF_BRIDGE_EXAMPLES_BODY",
		},
	)
	writeSkill(t, ws, "wireless", "WIRELESS_INDEX_BODY",
		map[string]string{
			"wifi-setup.md": "REF_WIFI_BODY",
			"bridge-tcp.md": "REF_BRIDGE_TCP_BODY",
			"bluetooth.md":  "REF_BLUETOOTH_BODY",
		},
	)
	writeSkill(t, ws, "vision", "VISION_INDEX_BODY",
		map[string]string{
			"v4l2.md":      "REF_V4L2_BODY",
			"gstreamer.md": "REF_GSTREAMER_BODY",
			"opencv.md":    "REF_OPENCV_BODY",
		},
	)
	writeSkill(t, ws, "audio", "AUDIO_INDEX_BODY",
		map[string]string{
			"mic-record.md":   "REF_MIC_BODY",
			"audio-output.md": "REF_AUDIO_OUT_BODY",
		},
	)
	writeSkill(t, ws, "arduino-app-lab", "APPLAB_INDEX_BODY",
		map[string]string{
			"bricks.md": "REF_BRICKS_BODY",
			"deploy.md": "REF_DEPLOY_BODY",
		},
	)

	// Disable any inherited global / builtin roots so test output is deterministic.
	t.Setenv("QCLAW_BUILTIN_SKILLS", filepath.Join(ws, "no-such-dir"))
	t.Setenv("QCLAW_HOME", filepath.Join(ws, "fake-home"))

	return NewContextBuilder(ws)
}

func TestPreloadSkillsForMessage_BreatheLED(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Make the LED on pin 9 breathe — fade in and out smoothly.")
	mustContain(t, out, "SKETCH_INDEX_BODY", "REF_BREATHING_BODY", "HARDWARE_INDEX_BODY", "REF_PINOUT_BODY")
	mustNotContain(t, out, "REF_BLINK_BODY", "REF_SERVO_BODY", "REF_BUTTON_BODY", "REF_VOLTAGE_BODY")
}

func TestPreloadSkillsForMessage_Blink(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Write a sketch that blinks the built-in LED once per second.")
	mustContain(t, out, "SKETCH_INDEX_BODY", "REF_BLINK_BODY")
	mustNotContain(t, out, "REF_BREATHING_BODY", "REF_POT_BODY")
}

func TestPreloadSkillsForMessage_Potentiometer(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Read a potentiometer connected to A0 and print its value to the Serial Monitor.")
	mustContain(t, out, "SKETCH_INDEX_BODY", "REF_POT_BODY", "HARDWARE_INDEX_BODY", "REF_PINOUT_BODY")
}

func TestPreloadSkillsForMessage_Button(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("When a button on pin 2 is pressed, turn on the LED on pin 13; otherwise turn it off.")
	mustContain(t, out, "SKETCH_INDEX_BODY", "REF_BUTTON_BODY", "HARDWARE_INDEX_BODY", "REF_PINOUT_BODY")
}

func TestPreloadSkillsForMessage_PWMPins(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Which pins on the Uno Q can do PWM?")
	mustContain(t, out, "HARDWARE_INDEX_BODY", "REF_PINOUT_BODY")
	mustNotContain(t, out, "SKETCH_INDEX_BODY", "REF_BREATHING_BODY")
}

func TestPreloadSkillsForMessage_FiveVoltOnA0(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Can I connect a 5V sensor to A0?")
	mustContain(t, out, "HARDWARE_INDEX_BODY", "REF_PINOUT_BODY", "REF_VOLTAGE_BODY")
}

func TestPreloadSkillsForMessage_MPUvsMCU(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("What is the difference between the MPU and the MCU on the Uno Q?")
	mustContain(t, out, "HARDWARE_INDEX_BODY")
	mustNotContain(t, out, "REF_PINOUT_BODY", "REF_VOLTAGE_BODY", "REF_BREATHING_BODY")
}

func TestPreloadSkillsForMessage_LEDMatrixScroll(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Scroll 'QClaw' across the LED matrix.")
	mustContain(t, out, "LEDMATRIX_INDEX_BODY", "REF_SCROLLTEXT_BODY")
}

func TestPreloadSkillsForMessage_CompileUpload(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Compile and upload the blink sketch to the Uno Q board.")
	mustContain(t, out, "SKETCH_INDEX_BODY", "REF_BLINK_BODY", "REF_UPLOAD_BODY")
}

// --- Wave 1: bridge + wireless + connectors + power ---

func TestPreloadSkillsForMessage_BridgeKeyword(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("How do I use Bridge to call my Arduino sketch from Python?")
	mustContain(t, out, "BRIDGE_INDEX_BODY", "REF_BRIDGE_PYTHON_BODY", "REF_BRIDGE_MCU_BODY", "REF_BRIDGE_EXAMPLES_BODY")
}

func TestPreloadSkillsForMessage_BridgePythonAndSketch(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Send sensor data from my sketch to a Python program.")
	mustContain(t, out, "BRIDGE_INDEX_BODY", "REF_BRIDGE_PYTHON_BODY")
}

func TestPreloadSkillsForMessage_WiFi(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Connect the board to Wi-Fi and POST sensor readings to a server.")
	mustContain(t, out, "WIRELESS_INDEX_BODY", "REF_WIFI_BODY", "REF_BRIDGE_TCP_BODY", "REF_BLUETOOTH_BODY")
}

func TestPreloadSkillsForMessage_Bluetooth(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Set up a BLE GATT server that exposes readings to a phone.")
	mustContain(t, out, "WIRELESS_INDEX_BODY", "REF_BLUETOOTH_BODY")
}

func TestPreloadSkillsForMessage_Connectors(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Which header is JDIGITAL and what does Qwiic plug into?")
	mustContain(t, out, "HARDWARE_INDEX_BODY", "REF_CONNECTORS_BODY")
}

func TestPreloadSkillsForMessage_Power(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Can I power the board from a 12V battery on VIN?")
	mustContain(t, out, "HARDWARE_INDEX_BODY", "REF_POWER_BODY")
}

// --- Wave 2: vision + audio + app-lab ---

func TestPreloadSkillsForMessage_Vision(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Take a picture with the camera and run face detection on it.")
	mustContain(t, out, "VISION_INDEX_BODY", "REF_V4L2_BODY", "REF_GSTREAMER_BODY", "REF_OPENCV_BODY")
}

func TestPreloadSkillsForMessage_Gstreamer(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Record an H.264 video using GStreamer.")
	mustContain(t, out, "VISION_INDEX_BODY", "REF_GSTREAMER_BODY")
}

func TestPreloadSkillsForMessage_Audio(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Record audio from the microphone and play a WAV file.")
	mustContain(t, out, "AUDIO_INDEX_BODY", "REF_MIC_BODY", "REF_AUDIO_OUT_BODY")
}

func TestPreloadSkillsForMessage_VoiceControl(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Build a voice-controlled LED using speech recognition.")
	mustContain(t, out, "AUDIO_INDEX_BODY")
}

func TestPreloadSkillsForMessage_AppLab(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("How do I add a Brick to my App in Arduino App Lab?")
	mustContain(t, out, "APPLAB_INDEX_BODY", "REF_BRICKS_BODY", "REF_DEPLOY_BODY")
}

// --- Wave 3: CAN/DAC/OpAmp refs + modulino + linux-led ---

func TestPreloadSkillsForMessage_CAN(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Read frames off the CAN bus on D4 and D5.")
	mustContain(t, out, "SKETCH_INDEX_BODY", "REF_CAN_BODY")
}

func TestPreloadSkillsForMessage_DAC(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Generate a sine wave tone on A0 using the DAC.")
	mustContain(t, out, "SKETCH_INDEX_BODY", "REF_DAC_BODY")
}

func TestPreloadSkillsForMessage_OpAmp(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Use the OPAMP2 as a voltage follower for a high-impedance sensor.")
	mustContain(t, out, "SKETCH_INDEX_BODY", "REF_OPAMP_BODY")
}

func TestPreloadSkillsForMessage_Modulino(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("How do I use a Modulino Distance sensor?")
	mustContain(t, out, "MODULINO_INDEX_BODY")
}

func TestPreloadSkillsForMessage_LinuxLED(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Blink the red:user LED from a Python program with no sketch.")
	mustContain(t, out, "LINUXLED_INDEX_BODY")
}

func TestPreloadSkillsForMessage_NoMatch(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Hello, how are you today?")
	if out != "" {
		t.Fatalf("expected empty output for unrelated message, got %q", out)
	}
}

func TestPreloadSkillsForMessage_EmptyMessage(t *testing.T) {
	cb := setupPreloadTest(t)
	if out := cb.PreloadSkillsForMessage(""); out != "" {
		t.Fatalf("expected empty for empty message, got %q", out)
	}
	if out := cb.PreloadSkillsForMessage("   \n\t  "); out != "" {
		t.Fatalf("expected empty for whitespace message, got %q", out)
	}
}

func TestPreloadSkillsForMessage_Dedupe(t *testing.T) {
	// "breathe", "fade", "pin 9", "analogWrite" all hit overlapping rules —
	// the same sketch-patterns SKILL.md should only appear once.
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("breathe fade pin 9 analogWrite PWM")
	if strings.Count(out, "SKETCH_INDEX_BODY") != 1 {
		t.Fatalf("expected SKETCH_INDEX_BODY exactly once, got %d", strings.Count(out, "SKETCH_INDEX_BODY"))
	}
	if strings.Count(out, "HARDWARE_INDEX_BODY") != 1 {
		t.Fatalf("expected HARDWARE_INDEX_BODY exactly once, got %d", strings.Count(out, "HARDWARE_INDEX_BODY"))
	}
	if strings.Count(out, "REF_PINOUT_BODY") != 1 {
		t.Fatalf("expected REF_PINOUT_BODY exactly once, got %d", strings.Count(out, "REF_PINOUT_BODY"))
	}
}

func TestPreloadSkillsForMessage_MissingSkillIsNoOp(t *testing.T) {
	// Workspace with no skills installed: pre-router should silently return
	// the empty string rather than emitting an empty preamble.
	ws := t.TempDir()
	t.Setenv("QCLAW_BUILTIN_SKILLS", filepath.Join(ws, "no-such-dir"))
	t.Setenv("QCLAW_HOME", filepath.Join(ws, "fake-home"))
	cb := NewContextBuilder(ws)
	if out := cb.PreloadSkillsForMessage("breathe the LED on pin 9"); out != "" {
		t.Fatalf("expected empty for empty workspace, got %q", out)
	}
}

func TestPreloadSkillsForMessage_EnvDisablesPreroute(t *testing.T) {
	cb := setupPreloadTest(t)
	t.Setenv("QCLAW_DISABLE_PRELOAD", "1")
	out := cb.PreloadSkillsForMessage("Make the LED on pin 9 breathe — fade in and out smoothly.")
	if out != "" {
		t.Fatalf("expected empty output when QCLAW_DISABLE_PRELOAD=1, got %d chars", len(out))
	}
}

func TestPreloadSkillsForMessage_PreambleNamesPathsAndStops(t *testing.T) {
	cb := setupPreloadTest(t)
	out := cb.PreloadSkillsForMessage("Make the LED on pin 9 breathe.")

	// Preamble must literally name every loaded path so the model can pattern-match.
	mustContain(t, out,
		"DO NOT call read_file",
		"skills/sketch-patterns/SKILL.md",
		"skills/sketch-patterns/breathing.md",
		"skills/uno-q-hardware/SKILL.md",
		"skills/uno-q-hardware/pinout.md",
		"STOP",
	)
}

func mustContain(t *testing.T, haystack string, needles ...string) {
	t.Helper()
	for _, n := range needles {
		if !strings.Contains(haystack, n) {
			t.Fatalf("expected output to contain %q\nfull output:\n%s", n, haystack)
		}
	}
}

func mustNotContain(t *testing.T, haystack string, needles ...string) {
	t.Helper()
	for _, n := range needles {
		if strings.Contains(haystack, n) {
			t.Fatalf("expected output NOT to contain %q\nfull output:\n%s", n, haystack)
		}
	}
}
