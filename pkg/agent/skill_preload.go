package agent

import (
	"fmt"
	"os"
	"regexp"
	"strings"

	"github.com/laurenvil/Uno-QClaw/pkg/logger"
	"github.com/laurenvil/Uno-QClaw/pkg/utils"
)

// skillPreloadRule maps a regex pattern against the user message to a skill
// (and optional reference files inside that skill) that should be auto-injected
// into the system prompt for the current turn.
//
// Rationale: Qwen3-0.8B running locally does not reliably emit the
// read_file tool call even when SOUL.md and the skill description tell them to.
// The agent loop already has the skill text on disk; matching keywords in the
// user message lets us pre-load the right SKILL.md + reference file so the
// model has authoritative content in-context without depending on tool-calling.
type skillPreloadRule struct {
	pattern *regexp.Regexp
	skill   string
	refs    []string
}

// skillPreloadRules is evaluated in order on every user turn. Multiple rules
// may fire for one message; sections are deduped by (skill, ref) pair before
// being concatenated, so overlapping patterns don't double-load content.
//
// Patterns are case-insensitive and anchored on word boundaries to avoid
// matching mid-token (e.g. "blink" inside "blinkenlights" doesn't fire).
var skillPreloadRules = []skillPreloadRule{
	{
		pattern: regexp.MustCompile(`(?i)\b(breathe|breathing|breath|fade|fading|fades|dim|dimming)\b`),
		skill:   "sketch-patterns",
		refs:    []string{"breathing.md"},
	},
	{
		pattern: regexp.MustCompile(`(?i)\b(blink|blinks|blinking|flash|flashes|flashing)\b`),
		skill:   "sketch-patterns",
		refs:    []string{"blink.md"},
	},
	{
		pattern: regexp.MustCompile(`(?i)\b(button|buttons|switch|switches|press|pressed|pressing|INPUT_PULLUP)\b`),
		skill:   "sketch-patterns",
		refs:    []string{"button.md"},
	},
	{
		pattern: regexp.MustCompile(`(?i)(\b(pot|potentiometer|dial|knob|analogRead)\b|Serial\s*Monitor|Serial\.print)`),
		skill:   "sketch-patterns",
		refs:    []string{"potentiometer.md"},
	},
	{
		pattern: regexp.MustCompile(`(?i)\b(servo|servos|sweep|sweeping)\b`),
		skill:   "sketch-patterns",
		refs:    []string{"servo.md"},
	},
	{
		pattern: regexp.MustCompile(`(?i)(\bpin\b|\bpins\b|\b[DA]\d{1,2}\b|\bPWM\b|\banalogWrite\b|\bpinMode\b|\bdigitalWrite\b|\bdigitalRead\b)`),
		skill:   "uno-q-hardware",
		refs:    []string{"pinout.md"},
	},
	{
		pattern: regexp.MustCompile(`(?i)\b(3\.?3\s?V|5\s?V|voltage|ADC|safe to connect|safe to use|damage|damages|fry|fries|burn|burns|short)\b`),
		skill:   "uno-q-hardware",
		refs:    []string{"voltage-safety.md"},
	},
	{
		pattern: regexp.MustCompile(`(?i)\b(MPU|MCU|Linux\s+side|Arduino\s+side|STM32|STM32U585|Cortex-A53|Cortex-M33|QRB2210|RPC\s+Bridge|two\s+processors)\b`),
		skill:   "uno-q-hardware",
		refs:    nil,
	},
	{
		pattern: regexp.MustCompile(`(?i)(\b(sketch|sketches|\.ino|setup\(\)|loop\(\)|Zephyr|FQBN)\b|write a (program|sketch))`),
		skill:   "sketch-patterns",
		refs:    nil,
	},
	// LED matrix: scroll text, draw frames, animations on the built-in 12x8.
	// The "matrix" + "scroll" combination is unambiguous for this skill.
	{
		pattern: regexp.MustCompile(
			`(?i)(\b(LED[\s-]?matrix|LED_Matrix|Arduino_LED_Matrix|ArduinoGraphics)\b|` +
				`\b(scroll|scrolls|scrolling|marquee)\b|` +
				`\bmatrix\b.*\b(text|display|show|scroll|draw)\b|` +
				`\b(text|display|show|scroll|draw)\b.*\bmatrix\b)`,
		),
		skill: "led-matrix",
		refs:  []string{"scroll-text.md"},
	},
	// Arduino tool: compile / upload / flash / detect — when the user asks the
	// agent to actually run the sketch on the board, load sketch-patterns
	// (canonical templates) + upload.md (how to invoke the `arduino` tool).
	// Without upload.md the 0.8B model produces a correct sketch but emits
	// it as a markdown code block instead of calling the tool. The reference
	// shows the exact `tool_calls` JSON shape it should produce.
	{
		pattern: regexp.MustCompile(
			`(?i)\b(compile|compiles|compiling|upload|uploads|uploading|flash|flashes|flashing|` +
				`build the sketch|run it on the board|put it on the board|arduino-cli|run on (the )?(uno q|board))\b`,
		),
		skill: "sketch-patterns",
		refs:  []string{"upload.md"},
	},
	// Bridge (Wave 1): RPC between Python on the MPU and an Arduino sketch on
	// the MCU. Triggers on the obvious vocabulary plus the "Python + sketch"
	// combination that is the defining feature of the Uno Q.
	{
		pattern: regexp.MustCompile(
			`(?i)(\bBridge\b|\bRPC\b|\bremote procedure call\b|` +
				`\b(Python|MPU|Linux side)\b.*\b(MCU|sketch|Arduino side)\b|` +
				`\b(MCU|sketch|Arduino side)\b.*\b(Python|MPU|Linux side)\b|` +
				`\b(arduino_alvik|App Lab|Bridge\.begin|Bridge\.on|Bridge\.notify|Bridge\.poll)\b)`,
		),
		skill: "bridge",
		refs:  []string{"python-side.md", "mcu-side.md", "examples.md"},
	},
	// Wireless (Wave 1): Wi-Fi and Bluetooth on the Linux MPU side. The MCU
	// has no radio; everything network-shaped goes through Bridge.
	{
		pattern: regexp.MustCompile(
			`(?i)(\b(Wi-?Fi|wifi|wireless|802\.11|WPA|SSID|hotspot)\b|` +
				`\b(Bluetooth|BLE|GATT|bluez|bleak)\b|` +
				`\b(network|networking|HTTP request|HTTPS|TCP|UDP|MQTT|WebSocket|REST API)\b|` +
				`\b(send (data|sensor data|readings) (to|over)|post to (a|an) (URL|API|server)|connect to (the )?internet)\b|` +
				`\b(NetworkManager|nmcli|wpa_supplicant|hostname|IP address)\b)`,
		),
		skill: "wireless",
		refs:  []string{"wifi-setup.md", "bridge-tcp.md", "bluetooth.md"},
	},
	// Hardware connectors (Wave 1): expose the seven-connector overview when
	// users ask about headers by name or by role.
	{
		pattern: regexp.MustCompile(
			`(?i)\b(JDIGITAL|JANALOG|JSPI|JMEDIA|JMISC|JCTL|Qwiic|QWIIC|header|headers|connector|connectors|carrier( board)?|shield)\b`,
		),
		skill: "uno-q-hardware",
		refs:  []string{"connectors.md"},
	},
	// Power (Wave 1): USB-C PD, VIN 7-24 V, 5V pin, voltage rails.
	{
		pattern: regexp.MustCompile(
			`(?i)\b(USB-?C( power| PD)?|Power Delivery|VBUS|VIN|7-24 ?V|7 to 24 ?V|battery|barrel jack|wall (wart|adapter)|brown-?out|brownout|power supply|amp (rating|draw)|milliamp|mA draw|stall current)\b`,
		),
		skill: "uno-q-hardware",
		refs:  []string{"power.md"},
	},
	// Vision (Wave 2): camera, V4L2, GStreamer, OpenCV, video codecs.
	{
		pattern: regexp.MustCompile(
			`(?i)(\b(camera|webcam|MIPI[- ]?CSI|CSI-?2|ISP|V4L2|/dev/video|GStreamer|gst-launch|OpenCV|cv2|video( frame|stream)?|image( capture)?|computer vision|machine vision|object detection|face detection|motion detection)\b|` +
				`\b(H\.?264|H\.?265|HEVC|VP9|h264parse|v4l2h264enc|v4l2h264dec)\b|` +
				`\btake a (picture|photo|snapshot|frame)\b|` +
				`\bcapture (a |an )?(image|frame|photo|picture|video))`,
		),
		skill: "vision",
		refs:  []string{"v4l2.md", "gstreamer.md", "opencv.md"},
	},
	// Audio (Wave 2): microphone, headphone, line out, ALSA, voice.
	{
		pattern: regexp.MustCompile(
			`(?i)(\b(microphone|mic|Mic2|headphone|earpiece|line ?out|line in|speaker|audio|ALSA|aplay|arecord|amixer|sound|sox|WAV|MP3|OGG|FLAC|sounddevice|simpleaudio|espeak|whisper|vosk|speech recognition)\b|` +
				`\b(text-?to-?speech|speech-?to-?text|voice[- ]?(recognition|control|controlled|command|activated))\b|` +
				`\b(play (a |an )?(sound|tone|song|recording))\b|` +
				`\brecord (audio|sound|the mic))`,
		),
		skill: "audio",
		refs:  []string{"mic-record.md", "audio-output.md"},
	},
	// App Lab (Wave 2): the App+Brick workflow that wraps Bridge.
	{
		pattern: regexp.MustCompile(
			`(?i)(\b(App Lab|AppLab|Arduino App Lab|Brick|Bricks|Run button|main\.py)\b|` +
				`\b(deploy (an? |the )?(App|project|sketch))\b|` +
				`\b(create (an? |the )?App)\b)`,
		),
		skill: "arduino-app-lab",
		refs:  []string{"bricks.md", "deploy.md"},
	},
	// CAN bus (Wave 3): FDCAN1 on D4/D5.
	{
		pattern: regexp.MustCompile(
			`(?i)\b(CAN[\s-]?bus|FDCAN|CAN-?FD|FDCAN1|OBD-?II|J1939|CANopen|CAN frame|CAN message|CAN_H|CAN_L)\b`,
		),
		skill: "sketch-patterns",
		refs:  []string{"can.md"},
	},
	// DAC (Wave 3): A0/A1 analog output.
	{
		pattern: regexp.MustCompile(
			`(?i)(\bDAC\b|\bDAC0\b|\bDAC1\b|\banalogWriteResolution\b|` +
				`\b(generate|output) (an? |the )?(tone|sine wave|waveform|function|analog (signal|voltage))\b|` +
				`\bfunction generator\b)`,
		),
		skill: "sketch-patterns",
		refs:  []string{"dac.md"},
	},
	// OpAmp (Wave 3): STM32U585 OPAMP1/OPAMP2.
	{
		pattern: regexp.MustCompile(
			`(?i)\b(OPAMP|OPAMP1|OPAMP2|op-?amp|operational amplifier|voltage follower|programmable gain amplifier|PGA gain|unity[- ]gain buffer)\b`,
		),
		skill: "sketch-patterns",
		refs:  []string{"opamp.md"},
	},
	// Modulino (Wave 3): Qwiic-connected Arduino sensors.
	{
		pattern: regexp.MustCompile(
			`(?i)\b(Modulino|Modulinos|ModulinoBuzzer|ModulinoDistance|ModulinoKnob|ModulinoMovement|ModulinoPixels|ModulinoThermo|ModulinoTouch)\b`,
		),
		skill: "modulino",
		refs:  nil,
	},
	// Linux LED (Wave 3): sysfs LED control from Python (MPU side LEDs).
	{
		pattern: regexp.MustCompile(
			`(?i)(\b(sysfs[- ]?LED|/sys/class/leds|red:user|green:user|blue:user|red:panic|green:wlan|blue:bt|brightness file)\b|` +
				`\b(Linux[- ]?(side )?LED|MPU[- ]?side LED|SoC LED|board LED from Python)\b)`,
		),
		skill: "linux-led",
		refs:  nil,
	},
}

// PreloadSkillsForMessage scans the user message against skillPreloadRules and
// returns a formatted block containing the relevant SKILL.md and reference
// file content. Empty string when no rule fires or the skill files are not
// installed (graceful no-op).
//
// The output is meant to be appended to the system prompt for this turn only
// — it is per-message and intentionally not cached.
//
// Setting QCLAW_DISABLE_PRELOAD=1 disables the pre-router entirely. Used by
// eval Run 3 Cell A to A/B with vs without the pre-router.
func (cb *ContextBuilder) PreloadSkillsForMessage(message string) string {
	if cb.skillsLoader == nil {
		return ""
	}
	if strings.TrimSpace(message) == "" {
		return ""
	}
	if os.Getenv("QCLAW_DISABLE_PRELOAD") == "1" {
		return ""
	}

	loadedSkill := make(map[string]bool)
	loadedRef := make(map[string]bool)
	var sections []string
	var firedSkills []string

	for _, rule := range skillPreloadRules {
		if !rule.pattern.MatchString(message) {
			continue
		}

		if !loadedSkill[rule.skill] {
			if content, ok := cb.skillsLoader.LoadSkill(rule.skill); ok {
				sections = append(sections, fmt.Sprintf("## %s/SKILL.md\n\n%s", rule.skill, strings.TrimSpace(content)))
				loadedSkill[rule.skill] = true
				firedSkills = append(firedSkills, rule.skill)
			}
		}

		for _, ref := range rule.refs {
			key := rule.skill + "/" + ref
			if loadedRef[key] {
				continue
			}
			if content, ok := cb.skillsLoader.LoadReference(rule.skill, ref); ok {
				sections = append(
					sections,
					fmt.Sprintf("## %s/references/%s\n\n%s", rule.skill, ref, strings.TrimSpace(content)),
				)
				loadedRef[key] = true
				firedSkills = append(firedSkills, key)
			}
		}
	}

	if len(sections) == 0 {
		return ""
	}

	logger.DebugCF("agent", "Skill pre-router fired",
		map[string]any{
			"loaded":          firedSkills,
			"section_count":   len(sections),
			"message_preview": utils.Truncate(message, 120),
		})

	// Build an explicit list of the SKILL.md / reference paths that follow,
	// so the preamble can name them in a STOP rule the model can pattern-match.
	// Models comply better with concrete negative imperatives than with vague
	// "you don't need to" hints — see eval v3 Run 2 finding (model called
	// read_file anyway on a path whose content was already inline).
	//
	// Iterate firedSkills (insertion order) rather than the dedupe maps so the
	// preamble matches the section order below, and the output is deterministic.
	var loadedPaths []string
	for _, fired := range firedSkills {
		if strings.Contains(fired, "/") {
			loadedPaths = append(loadedPaths, fmt.Sprintf("skills/%s", fired))
		} else {
			loadedPaths = append(loadedPaths, fmt.Sprintf("skills/%s/SKILL.md", fired))
		}
	}

	preamble := "# Auto-loaded References (DO NOT call read_file on these)\n\n" +
		"The full content of the following files is already shown verbatim below. " +
		"They have already been read for you:\n\n"
	for _, p := range loadedPaths {
		preamble += "  - `" + p + "`\n"
	}
	preamble += "\nSTOP — do not invoke `read_file` for any path in the list above. " +
		"Calling `read_file` on these paths is wasted work and adds 4–8 minutes of latency per call. " +
		"Use the content shown below directly. When a canonical sketch template appears in a reference section, " +
		"copy it byte-for-byte and change only the pin number / value the user requested."

	return preamble + "\n\n" + strings.Join(sections, "\n\n---\n\n")
}
