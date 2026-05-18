# QClaw v3 — Capability Integration Record (Waves 1–3)

**Date:** 2026-05-16
**Branch:** `qclaw-v3`
**Predecessor:** `docs/QClaw/capability-integration.md` — the inventory of Uno Q datasheet capabilities not covered by QClaw v3's initial surface.
**Scope:** Implementation record for the three waves that closed the identified gaps.

---

## Summary

| Wave | Theme | Skills added | Refs added | Tools added | Pre-router rules |
|---|---|---|---|---|---|
| **1** | Soul of the Uno Q | `bridge`, `wireless` | `connectors.md`, `power.md` | — | 4 |
| **2** | Vision / audio / App Lab | `vision`, `audio`, `arduino-app-lab` | — | `camera` | 3 |
| **3** | MCU peripherals + Linux surface | `modulino`, `linux-led` | `can.md`, `dac.md`, `opamp.md` | `sysfs_led`, `network`, `i2cdetect` | 5 |
| **Total** | | **7 new skills** | **5 new refs** | **4 new tools** | **12 new rules** |

Pre-router rule count: 11 → **23**.
Skill count: 8 → **15** (Uno Q-specific) + general inherited.
Tool surface: 4 → **8**, schema overhead ~1,800 → ~3,400 chars (still at v2's footprint, but with a broader and narrower-scoped capability set).

Tests: 21 → **36** in `pkg/agent/skill_preload_test.go`. All pass. Full `pkg/tools/` test suite clean (23.7 s).

---

## Wave 1 — Soul of the Uno Q

**Goal:** Stop treating the Uno Q like a classic Arduino with a Linux co-processor bolted on. Teach the dual-chip architecture and the wireless capabilities as first-class features.

### Skills added

**`workspace/skills/bridge/`** — the inter-processor RPC layer that makes the dual-chip architecture useful.

- `SKILL.md` — when to use Bridge, the App Lab project layout, quick rules, the relationship to `Serial.print` vs `Bridge.log`.
- `references/python-side.md` — `Bridge()` client construction, `bridge.call(...)`, `bridge.subscribe(...)`, `bridge.run_forever()`.
- `references/mcu-side.md` — `Bridge.begin()`, `Bridge.on(name, handler)`, `Bridge.notify()`, `Bridge.poll()`.
- `references/examples.md` — three complete worked projects: sensor relay, AI-driven actuator, button → web request.

**`workspace/skills/wireless/`** — Wi-Fi (WCN3980 on Linux) and Bluetooth (BlueZ).

- `SKILL.md` — explicitly states that the MCU has no radio; everything network-shaped goes through Bridge. Counters the common "I'll just `#include <WiFi.h>`" reflex from UNO R4 WiFi tutorials.
- `references/wifi-setup.md` — NetworkManager / nmcli flow, static IP for deployment deployments, diagnostics.
- `references/bridge-tcp.md` — the canonical sketch → Bridge → Python → HTTP/MQTT/WebSocket pattern.
- `references/bluetooth.md` — Bluetooth Classic vs BLE, BlueZ stack, `bleak` (client) and `bless` (GATT server) Python wrappers, full BLE GATT server example.

### Reference files added under `uno-q-hardware/`

- `references/connectors.md` — the seven-connector overview (JDIGITAL, JANALOG, JSPI, Qwiic, JCTL, JMISC, JMEDIA) with voltage domain (1.8 V / 3.3 V / mixed) and owner (MPU / MCU) for each. Use-case guide ("I want to plug in a sensor", "I want to drive an HDMI monitor"). Voltage domain map.
- `references/power.md` — the three power inputs (USB-C PD 5V/3A, VIN 7–24 V, 5V pin), on-board voltage rails (5V_SYS / PWR_3P8V / PWR_3P3V / VREG_L15A_1P8V), recommended operating conditions, motor/servo separation. Brown-out diagnostics.

### Pre-router rules added

| Pattern (case-insensitive) | Loads |
|---|---|
| `Bridge` / `RPC` / `remote procedure call` / Python+sketch cross-pattern / `arduino_alvik` / `App Lab` / `Bridge.begin/on/notify/poll` | `bridge` + 3 refs |
| `Wi-Fi` / `wifi` / `802.11` / `WPA` / `SSID` / `Bluetooth` / `BLE` / `GATT` / `network` / `HTTP request` / `HTTPS` / `TCP` / `UDP` / `MQTT` / `WebSocket` / `REST API` / `send data over` / `NetworkManager` / `nmcli` / `IP address` | `wireless` + 3 refs |
| `JDIGITAL` / `JANALOG` / `JSPI` / `JMEDIA` / `JMISC` / `JCTL` / `Qwiic` / `header(s)` / `connector(s)` / `carrier` / `shield` | `uno-q-hardware` + `connectors.md` |
| `USB-C` / `Power Delivery` / `VBUS` / `VIN` / `7-24 V` / `battery` / `barrel jack` / `wall adapter` / `brownout` / `power supply` / `mA draw` / `stall current` | `uno-q-hardware` + `power.md` |

(Bridge's regex also covers the "Python + sketch" cross-pattern as alternation branches within the single rule — counted as one rule, not separate entries.)

4 rules, 6 test cases.

---

## Wave 2 — Vision, audio, App Lab

**Goal:** Cover the marketed-target-area capabilities — Machine Vision, Voice-controlled systems, Edge AI & ML — by teaching the V4L2 / GStreamer / OpenCV / ALSA / App Lab + Bricks stack.

### Skills added

**`workspace/skills/vision/`** — computer vision on the Linux MPU side.

- `SKILL.md` — MIPI-CSI-2 vs USB webcam, V4L2 device enumeration, dual ISPs (13+13 MP or 25 MP @ 30 fps), Adreno 702 hardware codecs.
- `references/v4l2.md` — `/dev/video*` enumeration, `v4l2-ctl` commands, raw V4L2 from Python, hardware codec device discovery.
- `references/gstreamer.md` — canonical pipelines for capture, hardware-encoded H.264/H.265 recording, hardware-decoded playback (`v4l2h264dec`, `v4l2h265dec`, `v4l2vp9dec`), RTSP streaming, concurrent encode+decode.
- `references/opencv.md` — `cv2.VideoCapture` patterns, motion detection, face detection with Bridge integration, GStreamer pipeline as `VideoCapture` source for hardware-accelerated decode.

**`workspace/skills/audio/`** — analog audio endpoints exposed on JMISC.

- `SKILL.md` — Mic2 / Headphone / LineOut / Earpiece / HS_DET pins, ALSA-only access (MCU has no audio path), use cases (voice control, button → sound, audio-reactive light show).
- `references/mic-record.md` — `arecord` flags, `sounddevice` Python library, real-time chunked capture for whisper.cpp / vosk, Bridge integration ("loud sound triggers MCU action").
- `references/audio-output.md` — `aplay`, `mpg123`, `simpleaudio`, tone generation, text-to-speech via `espeak-ng` / `pyttsx3`, headphone vs LineOut routing.

**`workspace/skills/arduino-app-lab/`** — the App Lab IDE workflow.

- `SKILL.md` — App vs Brick vs Bridge, where QClaw fits, decision matrix for "QClaw vs App Lab".
- `references/bricks.md` — what Bricks are, how they're managed, when to use one vs write it yourself.
- `references/deploy.md` — the full Run-button lifecycle (cross-compile → OpenOCD flash → Python launch → Brick start → Bridge init), the three console tabs (Start-up / Main / Sketch), PC-hosted vs SBC mode.

### Tool added: `camera`

**Source:** `pkg/tools/camera.go`.

V4L2 single-frame capture via `gst-launch-1.0`. Pipeline shape is fixed:

```
v4l2src device=<device> num-buffers=1
  ! video/x-raw,width=<W>,height=<H>
  ! videoconvert
  ! jpegenc
  ! filesink location=<output>
```

Argument validation:
- `device` must start with `/dev/video` (rejects arbitrary paths).
- `width` and `height` must be ≤ 4096.
- `output` must resolve to a path under `/tmp/`, `/var/tmp/`, or `$HOME` (rejects writes to `/etc`, `/usr`, etc.).
- Defaults: `/dev/video0`, 1280×720, unique `/tmp/qclaw-camera-*.jpg`.

Linux-only (returns `ErrorResult` on macOS / Windows). 30-second timeout.

Return shape:

```
Captured 1280×720 frame from /dev/video0.
Saved to: /tmp/qclaw-camera-XXX.jpg (47821 bytes).
View with: feh /tmp/qclaw-camera-XXX.jpg  OR  scp it to a host with an image viewer.
```

### Pre-router rules added

| Pattern (case-insensitive) | Loads |
|---|---|
| `camera` / `webcam` / `MIPI-CSI` / `CSI-2` / `ISP` / `V4L2` / `/dev/video` / `GStreamer` / `gst-launch` / `OpenCV` / `cv2` / `video frame` / `videostream` / `image capture` / `computer vision` / `machine vision` / `object detection` / `face detection` / `motion detection` / `H.264` / `H.265` / `HEVC` / `VP9` / `take a picture/photo/snapshot/frame` / `capture an image/frame/video` | `vision` + 3 refs |
| `microphone` / `mic` / `Mic2` / `headphone` / `earpiece` / `lineout` / `speaker` / `audio` / `ALSA` / `aplay` / `arecord` / `amixer` / `WAV` / `MP3` / `OGG` / `FLAC` / `sounddevice` / `simpleaudio` / `espeak` / `whisper` / `vosk` / `text-to-speech` / `speech-to-text` / `voice control[led]` / `play a sound/tone/song/recording` / `record audio/sound/the mic` | `audio` + 2 refs |
| `App Lab` / `AppLab` / `Arduino App Lab` / `Brick(s)` / `Run button` / `main.py` / `deploy an App/project/sketch` / `create an App` | `arduino-app-lab` + 2 refs |

3 rules, 5 test cases.

---

## Wave 3 — MCU peripherals + Linux-side surface

**Goal:** Complete coverage of the MCU's specialty peripherals (CAN, DAC, OpAmp) and add narrow Linux-side tools for the everyday questions QClaw users ask ("blink the red user LED", "what's my IP", "what's on I²C").

### References added under `sketch-patterns/`

- `references/can.md` — FDCAN1 on D4/D5 with TJA1051T/3 transceiver wiring, receive sketch, transmit sketch, bus-speed table (OBD-II / CANopen / J1939 / CAN-FD), pitfalls (no transceiver = dead bus, missing termination).
- `references/dac.md` — A0/DAC0 and A1/DAC1 as 12-bit DAC outputs, steady-voltage example, sine-wave generator at 440 Hz with `analogWriteResolution(12)`, slow ramp, "when NOT to use the DAC" guidance.
- `references/opamp.md` — STM32U585's integrated OPAMP1 (JMISC) and OPAMP2 (A2/A3/D3) via `HAL_OPAMP_*`, voltage-follower example, ×4 PGA example, power-supply mode guidance.

### Skills added

**`workspace/skills/modulino/`** — Arduino Modulino plug-and-play sensors.

- `SKILL.md` — the seven standard Modulinos (Buzzer 0x3C, Distance 0x29, Knob 0x76, Movement 0x6A, Pixels 0x6C, Thermo 0x44, Touch 0x5A), `Modulino.begin()` + per-class begin pattern, single-sensor and multi-sensor sketches, address-collision pitfall.

**`workspace/skills/linux-led/`** — sysfs LED control from Python (MPU-side LEDs, no sketch).

- `SKILL.md` — the LED map (RGB LED 1/2 owned by MPU at `/sys/class/leds/*:user|panic|wlan|bt`, RGB LED 3/4 owned by MCU), **active-low inversion** rule, basic blink, color cycle, `udev` rule for non-root access, kernel trigger modes (`heartbeat`, `disk-activity`, etc.).

### Tools added

**`pkg/tools/sysfs_led.go`** — LED class subsystem.

Actions: `list` / `set` / `trigger`. Validates `led` argument against actual sysfs entries (no path traversal). User-facing `brightness` is 0..255 in **natural sense** (0 = off, 255 = on); the tool inverts internally to match active-low hardware. Scales to each LED's actual `max_brightness` (some are 0..1, some 0..255).

**`pkg/tools/network.go`** — read-only network state.

Actions: `summary` (default) / `interfaces` / `gateway`. Pure Go stdlib (`net.Interfaces()` for IPs and MACs, `/proc/net/route` parser for the default gateway). No shell-out. Returns hostname, per-interface IPs with flags, default gateway IP and interface.

**`pkg/tools/i2cdetect.go`** — Linux I²C bus enumeration and scan.

Actions: `list` (enumerate `/dev/i2c-*` with adapter names from `/sys/class/i2c-dev/*/name`) / `scan` (run `i2cdetect -y -r <bus>` for read-only SMBus-byte probing). Validates bus number range (0..99), confirms `/dev/i2c-N` exists before exec, 10-second timeout. Read-only by design — no i2cset / i2cget exposed.

### Pre-router rules added

| Pattern (case-insensitive) | Loads |
|---|---|
| `CAN bus` / `FDCAN` / `CAN-FD` / `OBD-II` / `J1939` / `CANopen` / `CAN frame` / `CAN message` / `CAN_H` / `CAN_L` | `sketch-patterns` + `can.md` |
| `DAC` / `DAC0` / `DAC1` / `analogWriteResolution` / `generate/output a tone/sine wave/waveform/analog signal/voltage` / `function generator` | `sketch-patterns` + `dac.md` |
| `OPAMP` / `OPAMP1` / `OPAMP2` / `op-amp` / `operational amplifier` / `voltage follower` / `PGA gain` / `unity-gain buffer` | `sketch-patterns` + `opamp.md` |
| `Modulino` / `ModulinoBuzzer` / `ModulinoDistance` / `ModulinoKnob` / `ModulinoMovement` / `ModulinoPixels` / `ModulinoThermo` / `ModulinoTouch` | `modulino` (SKILL.md only) |
| `sysfs-LED` / `/sys/class/leds` / `red:user` / `green:user` / `blue:user` / `red:panic` / `green:wlan` / `blue:bt` / `brightness file` / `Linux-side LED` / `MPU-side LED` / `SoC LED` / `board LED from Python` | `linux-led` (SKILL.md only) |

5 rules, 5 test cases.

---

## Combined inventory after all three waves

### Pre-router rules (23 total in `pkg/agent/skill_preload.go`)

| # | Trigger summary | Skill + refs | Wave |
|---|---|---|---|
| 1 | breathe / fade / dim | sketch-patterns + breathing.md | 0 |
| 2 | blink / flash | sketch-patterns + blink.md | 0 |
| 3 | button / INPUT_PULLUP | sketch-patterns + button.md | 0 |
| 4 | pot / analogRead / Serial Monitor | sketch-patterns + potentiometer.md | 0 |
| 5 | servo / sweep | sketch-patterns + servo.md | 0 |
| 6 | pin / PWM / D[0-21] / A[0-5] | uno-q-hardware + pinout.md | 0 |
| 7 | voltage / 5V / 3.3V / damage | uno-q-hardware + voltage-safety.md | 0 |
| 8 | MPU / MCU / STM32 / QRB2210 | uno-q-hardware | 0 |
| 9 | sketch / .ino / setup() / loop() | sketch-patterns | 0 |
| 10 | LED matrix / scroll / marquee | led-matrix + scroll-text.md | 0 |
| 11 | compile / upload / flash / arduino-cli | sketch-patterns + upload.md | 0 |
| 12 | Bridge / RPC / Python + sketch | bridge + 3 refs | 1 |
| 13 | Wi-Fi / Bluetooth / network / HTTP | wireless + 3 refs | 1 |
| 14 | JDIGITAL / JANALOG / Qwiic / header | uno-q-hardware + connectors.md | 1 |
| 15 | USB-C / VIN / power / battery | uno-q-hardware + power.md | 1 |
| 16 | camera / V4L2 / GStreamer / OpenCV | vision + 3 refs | 2 |
| 17 | microphone / audio / voice / ALSA | audio + 2 refs | 2 |
| 18 | App Lab / Brick / Run button | arduino-app-lab + 2 refs | 2 |
| 19 | CAN bus / FDCAN / OBD-II | sketch-patterns + can.md | 3 |
| 20 | DAC / sine wave / function generator | sketch-patterns + dac.md | 3 |
| 21 | OPAMP / voltage follower / PGA | sketch-patterns + opamp.md | 3 |
| 22 | Modulino[Buzzer/Distance/…] | modulino | 3 |
| 23 | sysfs LED / red:user / blue:bt | linux-led | 3 |

### Tools (8 enabled in `config/qclaw.config.json`)

| Tool | Source | Linux-only | Validation | Wave |
|---|---|---|---|---|
| `read_file` | `pkg/tools/filesystem.go` | No | `max_read_file_size` | 0 |
| `write_file` | `pkg/tools/filesystem.go` | No | path allow-list via `allow_write_paths` | 0 |
| `list_dir` | `pkg/tools/filesystem.go` | No | path allow-list | 0 |
| `arduino` | `pkg/tools/arduino.go` | Yes | Fixed FQBN, fixed OpenOCD address `0x8100000` | 0 |
| `camera` | `pkg/tools/camera.go` | Yes | `/dev/video*` device prefix, ≤4096 res, output path in /tmp/$HOME | 2 |
| `sysfs_led` | `pkg/tools/sysfs_led.go` | Yes | LED name must exist in `/sys/class/leds`; brightness 0..255; trigger must be in published list | 3 |
| `network` | `pkg/tools/network.go` | Yes | Read-only; pure stdlib | 3 |
| `i2cdetect` | `pkg/tools/i2cdetect.go` | Yes | Bus number 0..99, device must exist; `-y -r` (no `-q`, no writes) | 3 |

### Skills (15 Uno Q-specific in `workspace/skills/`)

| Skill | Refs | Wave |
|---|---|---|
| `sketch-patterns` | 9 (breathing, blink, button, potentiometer, servo, upload, **can**, **dac**, **opamp**) | 0 + 3 |
| `led-matrix` | 1 (scroll-text) | 0 |
| `uno-q-hardware` | 4 (pinout, voltage-safety, **connectors**, **power**) | 0 + 1 |
| `bridge` | 3 (python-side, mcu-side, examples) | 1 |
| `wireless` | 3 (wifi-setup, bridge-tcp, bluetooth) | 1 |
| `vision` | 3 (v4l2, gstreamer, opencv) | 2 |
| `audio` | 2 (mic-record, audio-output) | 2 |
| `arduino-app-lab` | 2 (bricks, deploy) | 2 |
| `modulino` | 0 (SKILL.md only) | 3 |
| `linux-led` | 0 (SKILL.md only) | 3 |
| (+ general inherited: github, skill-creator, summarize, tmux, weather) | — | inherited |

---

## Cross-cutting design decisions

### Why narrow per-domain tools instead of re-enabling `exec`

The gap analysis identified three trade-offs (`exec` vs narrow tools, pre-router KV pressure, 0.8B quality ceiling). The implementation took the narrow-tool path for every Wave 2/3 capability:

- **Camera** — fixed GStreamer pipeline shape with allow-list-validated arguments, not "run any shell command."
- **Sysfs LED** — LED name validated against actual sysfs entries; brightness handles active-low inversion internally so the model doesn't need to know.
- **Network** — pure Go stdlib + `/proc/net/route` parser. Zero shell-out, zero attack surface.
- **I²C detect** — wraps a single `i2cdetect -y -r` invocation with bus-range validation; no `i2cset`/`i2cget`.

Result: 8 tools, ~3,400-char schema overhead, no general shell capability. Compared to `exec` re-enablement this is more verbose to maintain (4 separate Go files) but materially safer for deployment deployment.

### Pre-router KV pressure (still relevant)

The Wave 1-3 additions don't change the worst-case prompt size — only the *matched* skills inline content, and no single user message fires all 23 rules. The largest realistic match is the LED-matrix + compile/upload combination (~11K of pre-router content), which is comparable to what Run 7/8 already exercised.

**No mitigation needed at this time.** If a future skill triggers along with the existing largest ones and pushes total prompt past 22-23K chars, the fan-out cap proposed in the gap analysis (cap to ~3 matched skills per message, deduplicate less-specific matches) should ship before that wave.

### 0.8B quality ceiling on niche topics

Run 8 demonstrated the 0.8B will hallucinate ("LCD" for the LED matrix) even with the SKILL.md inlined. Bridge and vision are more complex than LED matrix; expect similar quality regressions on edge cases.

Mitigations applied in the new skill content:
- Every new SKILL.md includes a **Pitfalls** section that names the specific misconception the model is likely to produce ("`#include <WiFi.h>` will not compile", "treating the Uno Q like a Raspberry Pi", "confusing CCI I²C with user I²C").
- The Bridge skill explicitly states "the MCU has no Wi-Fi peripheral" four times across the SKILL.md + 3 references because that's the most likely confusion.
- The wireless skill includes a copy-paste-ready denial of the UNO R4 WiFi pattern at the top.

Whether this is enough is an empirical question for a future Run 9.

---

## Files added or modified

### Skills tree (`workspace/skills/`)

```
bridge/
  SKILL.md                                  NEW
  references/{python-side,mcu-side,examples}.md   NEW
wireless/
  SKILL.md                                  NEW
  references/{wifi-setup,bridge-tcp,bluetooth}.md NEW
vision/
  SKILL.md                                  NEW
  references/{v4l2,gstreamer,opencv}.md     NEW
audio/
  SKILL.md                                  NEW
  references/{mic-record,audio-output}.md   NEW
arduino-app-lab/
  SKILL.md                                  NEW
  references/{bricks,deploy}.md             NEW
modulino/
  SKILL.md                                  NEW
linux-led/
  SKILL.md                                  NEW
sketch-patterns/references/
  can.md                                    NEW
  dac.md                                    NEW
  opamp.md                                  NEW
uno-q-hardware/references/
  connectors.md                             NEW
  power.md                                  NEW
```

### Go code

```
pkg/agent/skill_preload.go        +13 rules
pkg/agent/skill_preload_test.go   +15 tests
pkg/agent/loop.go                 +4 tool registrations
pkg/config/config.go              +4 ToolConfig entries, +4 IsToolEnabled cases
pkg/tools/camera.go               NEW (~150 lines)
pkg/tools/sysfs_led.go            NEW (~180 lines)
pkg/tools/network.go              NEW (~110 lines)
pkg/tools/i2cdetect.go            NEW (~130 lines)
```

### Config

```
config/qclaw.config.json         +4 enabled-true blocks (camera/sysfs_led/network/i2cdetect)
```

### Tests

| Test | Pass status |
|---|---|
| `TestPreloadSkillsForMessage_*` (36 total) | 36/36 ✅ |
| `pkg/tools/` package suite | All pass (23.7s) |
| `go build ./...` | Clean |

---

## What this does NOT do

- **No SOUL.md tool-call imperative** to close the ambient-prompt gap from Run 7. That's a separate fix orthogonal to the capability waves. Adding "always call the arduino tool when the user asks to upload" to SOUL.md is the recommended next step but was kept out of this work to isolate the capability variable.
- **No new evaluation runs.** Run 9 (re-run the standard prompt battery against the 8-tool surface, plus 3 new prompts that exercise camera/sysfs_led/network/i2cdetect) is the canonical empirical follow-up.
- **No pre-router fan-out cap.** Recommended in the gap analysis as a Wave 2-time mitigation; not strictly needed yet (no realistic message fires all 23 rules), but should ship before Ventuno Q work begins.
- **No `<skills>` XML in the Direct-path REPL.** The eval driver (`eval_v8_direct_preroute.py`) includes it; the production REPL (`scripts/qclaw-direct-chat.py`) omits it to save ~600 chars. The Run 8 quality regressions occurred *with* the XML present, so this is a minor difference, not a quality lever.

---

## See also

- `docs/QClaw/capability-integration.md` — the prior doc that motivated this work.
- `docs/QClaw/whitepaper.md` — overall v3 architecture and evaluation rationale.
- `docs/QClaw/whitepaper.md` — agentic-path baseline before the wave additions.
- `docs/QClaw/whitepaper.md` — direct-path baseline before the wave additions.
- `pkg/agent/skill_preload.go` — current authoritative rule list (23 entries).
- `config/qclaw.config.json` — current authoritative tool enable/disable list.
