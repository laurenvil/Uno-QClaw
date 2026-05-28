# QClaw Architecture Study Bible

How QClaw turns a user's natural language question into working Arduino code on the Uno Q board, then compiles and flashes that code to the microcontroller. This document is for both developers working on QClaw and for users who want to understand how the system works under the hood.

**QClaw-v2 architecture summary:** QClaw ships two execution paths sharing the same model, system prompt, and 15-skill tree, both driven by the persistent **`pkg/providers/llamaserver`** provider (a long-lived llama-server child on 127.0.0.1):
- **Agentic** — agent loop + 23-rule pre-router + **8 tools** (`read_file`, `write_file`, `list_dir`, `arduino`, `camera`, `sysfs_led`, `network`, `i2cdetect`). End-to-end compile/flash, camera capture, MPU LED control, network diagnostics, I²C bus scan. `make qclaw-agentic` / `make qclaw`.
- **Direct** — same 23-rule pre-router + single LLM call, no tools, no loop. Faster Q&A across all 15 skills; cannot perform hardware actions. `make qclaw-direct` / `qclaw direct` (native Go: `ProcessDirectSingleTurn` in `pkg/agent/loop.go`, `cmd/qclaw/internal/agent/direct.go`).

**Engine selection is config-only.** The default engine is `yzma` ⭐ (b9127, self-contained at `engines/yzma/lib/`), selected via `agents.defaults.model_name` or `--model yzma`. Additional engines can be added by dropping a `llama-server` binary and a `model_list` entry — no Go rebuild. See **Part 7** for the full provider/config reference and **Part 3** for the data-path walkthrough.

The 15 skills are organized into three domains:
- **Sketch-side** (MCU): `sketch-patterns`, `led-matrix`, `uno-q-hardware`
- **Bridge-side** (cross-chip): `bridge`, `arduino-app-lab`
- **Linux-side** (MPU): `wireless`, `vision`, `audio`, `linux-led`, `modulino` (+ inherited general skills)

The full evaluation rationale lives in `docs/QClaw/whitepaper.md`. The capability gap analysis that motivated the 7 new skills and 4 new tools is in `docs/QClaw/capability-integration.md`; the implementation record is in `docs/QClaw/capability-integration.md`.

---

## Part 1: The Hardware — Arduino Uno Q

### The Big Picture: Two Brains, One Board

The Arduino Uno Q is not a single computer. It is two computers on one board that talk to each other.

```
┌────────────────────────────────────────────────────────────┐
│                    Arduino Uno Q                            │
│                                                             │
│  ┌──────────────────────┐    Bridge (RPC)    ┌──────────┐  │
│  │  MPU — Linux Side    │◄──────────────────►│  MCU     │  │
│  │  Qualcomm QRB2210    │   USB CDC / UART   │ STM32U585│  │
│  │  Cortex-A53 × 4      │                   │Cortex-M33│  │
│  │  2.0 GHz, 4 GB RAM   │                   │160 MHz   │  │
│  │  Debian Linux        │                   │Arduino   │  │
│  │                      │                   │Core +    │  │
│  │  ► QClaw lives here │                   │Zephyr OS │  │
│  │  ► Python programs   │                   │          │  │
│  │  ► AI inference      │                   │► Sketches│  │
│  │  ► OpenCV / web      │                   │► GPIO    │  │
│  │  ► llama-server      │                   │► PWM/ADC │  │
│  │     (yzma b9127)     │                   │          │  │
│  └──────────────────────┘                   └──────────┘  │
│                                                             │
│  1.8 V I/O domain (MPU)        3.3 V I/O domain (MCU)      │
└────────────────────────────────────────────────────────────┘
```

### The MPU: Where QClaw Lives

| Attribute | Detail |
|-----------|--------|
| Chip | Qualcomm Dragonwing QRB2210 |
| CPU | 4× ARM Cortex-A53 @ 2.0 GHz (64-bit) |
| GPU | Adreno 702 @ 845 MHz — OpenGL, Vulkan, OpenCL 2.0 |
| RAM | 2 GB or 4 GB LPDDR4X |
| Storage | 16 GB or 32 GB eMMC |
| OS | Debian Linux |
| I/O voltage | **1.8 V** (NOT accessible from Arduino sketches) |
| Wireless | Wi-Fi 5 (802.11a/b/g/n/ac) + Bluetooth 5.1 |

The MPU handles everything Linux: running Python programs, serving web pages, processing camera images with OpenCV, running AI inference (via a persistent `llama-server` child process — by default `yzma/lib/llama-server` — managed by `pkg/providers/llamaserver` and proxied over 127.0.0.1), and hosting QClaw itself. Its GPIO pins operate at 1.8 V and are dedicated to system functions (camera control, display, audio). They are NOT the Arduino pins a user uses for their project.

### The MCU: Where Arduino Sketches Run

| Attribute | Detail |
|-----------|--------|
| Chip | STMicroelectronics STM32U585 |
| CPU | ARM Cortex-M33 @ up to 160 MHz |
| Flash | 2 MB |
| SRAM | 786 kB |
| OS | Zephyr RTOS + Arduino Core |
| I/O voltage | **3.3 V** |

The MCU is the real-time controller. It manages every Arduino pin on the headers: digital I/O, PWM, ADC, SPI, I2C, UART, CAN. When a user writes `digitalWrite(13, HIGH)`, that instruction runs on the STM32U585 — not on the Linux processor.

**This means Arduino sketches run on the MCU, not on Linux.**

### Bridge: The Communication Layer

Bridge is Arduino's RPC (Remote Procedure Call) library that connects the two processors. It lets either side call functions on the other:

- A Python script on Linux can call an MCU function to read a sensor
- An Arduino sketch can call a Linux service to log data or fetch AI inference

Physical transports: USB CDC (virtual serial port), UART, or SPI.

```
Python (Linux)                    Arduino Sketch (MCU)
─────────────────                 ─────────────────────
from bridge import ...            #include <Bridge.h>
sensor = bridge.call("read_A0")  Bridge.begin();
print(sensor)                    // expose a service
```

---

## Part 2: The Pin Map

### Headers and Their Owners

| Header | Label | Pins | Owner | Voltage | Purpose |
|--------|-------|------|-------|---------|---------|
| JDIGITAL | A2 | 18-pin | MCU | 3.3 V | Digital I/O, PWM, SPI, UART, CAN |
| JANALOG | A3 | 14-pin | MCU | 3.3 V | ADC, analog I/O, power |
| Qwiic | A4 | 4-pin | MCU | 3.3 V | I2C4 plug-and-play ecosystem |
| JSPI | A5 | 6-pin | MCU | 3.3 V | Dedicated SPI header |
| JCTL | A1 | 10-pin | MPU | 1.8 V | Boot, reset, console (not for user IO) |
| JMISC | B1 | 60-pin | Mixed | 1.8/3.3 V | Advanced: audio, MPU GPIO, MCU debug |
| JMEDIA | B2 | 60-pin | MPU | 1.8 V | MIPI camera, display (not for user IO) |

### JDIGITAL (A2) — Full Pin Reference

All pins are 3.3 V logic on the STM32U585. Tilde (~) means PWM-capable.

| Arduino Pin | STM32 Pin | Key Alternate Functions | Notes |
|-------------|-----------|-------------------------|-------|
| D0 (RX) | PB7 | USART1_RX | Serial RX |
| D1 (TX) | PB6 | USART1_TX, TIM4_CH2 | Serial TX |
| D2 | PB3 | TIM4_CH1 | GPIO |
| **~D3** | PB0 | **TIM2_CH2** (PWM), OPAMP2_OUT | PWM |
| D4 | PA12 | TIM3_CH3, FDCAN1_TX | CAN TX |
| **~D5** | PA11 | TIM1, FDCAN1_RX | PWM, CAN RX |
| **~D6** | PB1 | **TIM3_CH4, TIM8_CH4N** | PWM |
| D7 | PB2 | TIM3_CH1, TIM4_CH3 | GPIO |
| D8 | PB4 | TIM1 | GPIO |
| **~D9** | PB8 | **TIM4_CH4** | PWM |
| **~D10** | PB9 | **TIM1_CH4**, SPI2_SS | PWM, SPI Chip Select |
| **~D11** | PB15 | **TIM1_CH3N**, SPI2_MOSI | PWM, SPI MOSI |
| D12 | PB14 | TIM1_CH2N, SPI2_MISO | SPI MISO |
| D13 | PB13 | TIM1_CH1N, SPI2_SCK | SPI SCK |
| GND | — | — | Ground |
| AREF | PB11 | Analog reference (output, not GPIO) | Tied to 3.3 V |
| D20 (SDA) | — | I2C2_SDA, TIM2_CH4 | Wire SDA |
| D21 (SCL) | PB10 | I2C2_SCL, TIM2_CH3 | Wire SCL |

**SPI bus (D10–D13):** Standard Arduino SPI pinout. D10 = CS, D11 = MOSI, D12 = MISO, D13 = SCK.
**I2C bus (D20/D21):** `Wire.begin()` in a sketch uses I2C2 (SDA=D20, SCL=D21).
**UART (D0/D1):** `Serial.begin(9600)` accesses USART1. Note: D0/D1 are also the USB-serial passthrough on the classic Uno — on the Uno Q these map to USART1 on the MCU.
**CAN bus (D4/D5):** FDCAN1 is available on D4 (TX) and D5 (RX) for automotive/industrial applications.

### JANALOG (A3) — Full Pin Reference

⚠ **CRITICAL VOLTAGE DIFFERENCE FROM CLASSIC ARDUINO UNO:**
Classic Arduino Uno = 5 V ADC, 0–5 V input range.
Arduino Uno Q = 3.3 V ADC, **0–3.3 V input range**. A0–A5 are NOT 5 V-tolerant in ADC mode (absolute max: ~3.6 V). Applying 5 V will damage the MCU.

| Pin | STM32 | ADC Range | Alternate Functions | Notes |
|-----|-------|-----------|---------------------|-------|
| A0 / D14 | PA4 | 0–3.3 V | DAC0, TIM2_CH1 | Also a DAC output |
| A1 / D15 | PA5 | 0–3.3 V | DAC1, TIM3_CH1 | Also a DAC output |
| A2 / D16 | PA6 | 0–3.3 V | OPAMP2_INPUT+ | |
| A3 / D17 | PA7 | 0–3.3 V | OPAMP2_INPUT− | |
| A4 / D18 | PC1 | 0–3.3 V | **I2C3_SDA**, LPTIM1 | Wire2 SDA option |
| A5 / D19 | PC0 | — | **I2C3_SCL**, LPTIM1 | Wire2 SCL option |

`analogRead(A0)` returns 0–1023 (Arduino-compatible 10-bit mapping from the 12-bit STM32 ADC). Voltage = `(analogRead(A0) / 1023.0) * 3.3` volts.

### JSPI Header (A5) — Dedicated SPI

| Pin | Net | Notes |
|-----|-----|-------|
| 1 MISO | PC2 (SPI2_MISO) | 3.3 V |
| 2 +5V | 5V_SYS | Power only |
| 3 SCK | PD1 (SPI2_SCK) | 3.3 V |
| 4 MOSI | PC3 (SPI2_MOSI) | 3.3 V |
| 5 RESET | MCU_NRST | MCU reset |
| 6 GND | Ground | |

### Qwiic Connector (A4) — I2C4

4-pin JST connector for the Qwiic/Stemma QT ecosystem. Maps to I2C4 (PD13=SDA, PD12=SCL). Plug any Modulino sensor directly here — no breadboard, no soldering.

### On-Board LEDs

| LED | Controlled by | Pins | Access |
|-----|---------------|------|--------|
| RGB LED 1 (D27301) | MPU (Linux) | GPIO_41 (R), GPIO_42 (G), GPIO_60 (B) | `/sys/class/leds/red:user` etc. |
| RGB LED 2 (D27302) | MPU (Linux) | GPIO_39 (R), GPIO_40 (G), GPIO_47 (B) | Status: PANIC, WLAN, BT |
| RGB LED 3 (D27401) | MCU (Arduino) | PH10 (R), PH11 (G), PH12 (B) | `analogWrite` / `digitalWrite` from sketch |
| RGB LED 4 (D27402) | MCU (Arduino) | PH13 (R), PH14 (G), PH15 (B) | `analogWrite` / `digitalWrite` from sketch |
| LED Matrix (D27001–D27104) | MCU | — | **13 columns × 8 rows = 104 monochrome blue pixels**, boot logo |
| Power LED (D27201) | Hardware | — | On when 3.3 V is present |

All RGB LEDs are **active-low** (write `0` to turn on, `1` to turn off).

The Blink LED Hello World example uses RGB LED 3 (red channel) — this is MCU-driven and appears when the sketch runs on the STM32U585.

**LED Matrix API note:** The matrix is 13 wide × 8 tall (`canvasWidth=13, canvasHeight=8` per `Arduino_LED_Matrix.h`). The canonical scrolling-text template uses the 5-argument form of `beginText`:

```cpp
#include "ArduinoGraphics.h"        // must come FIRST
#include "Arduino_LED_Matrix.h"

Arduino_LED_Matrix matrix;

void setup() {
    matrix.begin();
    matrix.textFont(Font_5x7);
    matrix.textScrollSpeed(100);
    matrix.clear();
}

void loop() {
    matrix.beginText(0, 0, 127, 0, 0);   // x, y, R, G, B — 5-arg form
    matrix.print("      QClaw      "); // space-pad to start/end off-screen
    matrix.endText(SCROLL_LEFT);
    delay(1000);
}
```

The pre-router (Part 3, agentic path) inlines this template when the user message contains `matrix`, `scroll`, `Arduino_LED_Matrix`, or `ArduinoGraphics`. See `workspace/skills/led-matrix/SKILL.md` for the full reference.

### Flash Layout: Why `0x8100000` Matters

The STM32U585 has 2 MB of flash split into two 1 MB banks. Sketches must be written to the **bank 2 sketch partition** at `0x8100000` — not the reserved area at the end of bank 1 (`0x80F0000`).

| Region | Address range | Size | Contents |
|---|---|---|---|
| Bank 1, areas 1–7 | `0x08000000`–`0x080EFFFF` | 960 KB | Zephyr kernel + Arduino core |
| Bank 1, area 8 | `0x080F0000`–`0x080FFFFF` | 64 KB | Reserved (NOT executable as a sketch) |
| Bank 2 start | `0x08100000` | — | **Sketch partition (boards.txt: `unoq.upload.address`)** |
| Bank 2 remainder | `0x08100000`–`0x081FFFFF` | 1 MB | Sketch code + data |

The pre-installed `/usr/local/bin/arduino-flash` wrapper hardcodes `0x80F0000` and silently writes sketches into the reserved area, where they never execute. QClaw's arduino tool invokes OpenOCD directly at `0x8100000` to avoid this. Root-cause analysis: `docs/QClaw/whitepaper.md` §8.

---

## Part 3: How QClaw Works — The Three Data Paths

QClaw-v2 has three execution paths. They share the same llama-server engine, model, system prompt, and skills tree — they differ in what surrounds the LLM call and how the server lifetime is managed.

> **Implementation note (QClaw-v2).** All three paths use `pkg/providers/llamaserver`, a Go driver that **spawns one `llama-server` child process** (`engines/yzma/lib/llama-server`) and **keeps it up across requests**, proxying chat completions through 127.0.0.1 over the OpenAI-compatible `/v1/chat/completions` endpoint. The server is health-checked on `/health` before the first call. Only the first call per QClaw process pays the cold model-load cost (~3–5 min on Uno Q); follow-up turns skip mmap, kernel allocation, and warmup entirely. **Path C (TUI) additionally calls `WarmUp()` at startup**, so the server is ready before the first user message.

### Path A — Agentic (`make qclaw-agentic`)

When a user sends a Telegram message OR types at the agent terminal:

```
User input (Telegram / terminal / SSH)
    │
    ▼
qclaw channel adapter (pkg/channels/{telegram,cli,...}.go)
    │ For Telegram: sends "Asking QClaw..." immediately
    │ Publishes InboundMessage to the message bus
    ▼
Message Bus (pkg/bus/bus.go)
    │ Pub/sub — decouples channel from agent
    ▼
AgentLoop.processMessage() (pkg/agent/loop.go)
    │ resolveScopeKey() preserves --session <key> for multi-session isolation
    ▼
ContextBuilder.PreloadSkillsForMessage()  ← v3 pre-router
(pkg/agent/skill_preload.go)
    │ Scans the message against 23 keyword regex rules across 15 skills.
    │ For each match, inlines the relevant SKILL.md and reference files
    │ into a STOP preamble prepended to the system prompt — so the model
    │ does NOT have to call read_file to load skill content.
    │ Example: "scroll QClaw across the LED matrix" fires the led-matrix
    │ rule, inlines led-matrix/SKILL.md + scroll-text.md (~7K chars).
    ▼
ContextBuilder.BuildMessages() (pkg/agent/context.go)
    │ Assembles the cached system prompt:
    │   1. getIdentity() — hardcoded qclaw identity block
    │   2. SOUL.md — QClaw Arduino persona + minimal rules
    │   3. IDENTITY.md — QClaw name + purpose
    │   4. <skills> XML — index of all 15 available skills
    │   5. Pre-router preamble (STOP + inlined content from above)
    │   6. 8-tool JSON schema (~3,400 chars)
    │   7. Memory context (MEMORY.md if exists)
    │ Appends conversation history.
    ▼
llamaserver.Provider.Chat() (pkg/providers/llamaserver/provider.go)
    │ ensureServer(): on first call only —
    │   exec.Command(binary, args...) with:
    │     -m <modelPath>  --host 127.0.0.1  --port <port>
    │     -t <threads>    -c <ctxSize>      -np <parallel>
    │     --reasoning off  --jinja  --log-disable
    │     + any extra_args from config (e.g. --flash-attn on, --mlock,
    │                                   --cache-type-k/v q8_0,
    │                                   --reasoning-budget 800)
    │   cmd.Env injects LD_LIBRARY_PATH=<lib_path>:... for dynamically-linked builds
    │   Poll /health until 200 OK, then mark initialized=true.
    │   The child stays up for the lifetime of this QClaw process.
    │ Then on every call: forward to inner openai_compat.Provider
    ▼
HTTP POST 127.0.0.1:<port>/v1/chat/completions
    │ ChatStream variant streams SSE deltas live; non-stream variant
    │ blocks until [DONE] arrives. Tool-aware: when tools are passed,
    │ tool_calls deltas are accumulated indexed by their slot and emitted
    │ as one unit at end-of-stream.
    ▼
llama-server child (engines/yzma/lib/llama-server)
    │ Model: Qwen_Qwen3.5-0.8B-Q4_0 (~490 MB; mmap once at first /health)
    │ /no_think active in SOUL.md + --reasoning off → no reasoning preamble
    │ KV cache lives in the server's RSS across requests (~1.1 GB peak).
    │ Returns OpenAI-compatible JSON with content + tool_calls.
    ▼
openai_compat.Provider decodes the JSON into LLMResponse.
    │
    ▼
LLM response — content + tool_calls[]
    │
    ▼  if tool_calls is non-empty (iteration):
    │
ToolRegistry.ExecuteWithContext() (pkg/tools/registry.go)
    │ Dispatches to one of 8 registered tools:
    │   ├── read_file / write_file / list_dir  (pkg/tools/filesystem.go)
    │   ├── arduino    (pkg/tools/arduino.go)
    │   │    │  compile → arduino-cli compile --fqbn arduino:zephyr:unoq
    │   │    │  upload  → compile then OpenOCD flash @ 0x8100000
    │   │    │  detect  → arduino-cli board list
    │   ├── camera     (pkg/tools/camera.go)
    │   │    └── gst-launch-1.0 v4l2src ! videoconvert ! jpegenc ! filesink
    │   ├── sysfs_led  (pkg/tools/sysfs_led.go)
    │   │    └── list / set brightness / set trigger on /sys/class/leds/*
    │   ├── network    (pkg/tools/network.go)
    │   │    └── net.Interfaces + /proc/net/route default-gateway parse
    │   └── i2cdetect  (pkg/tools/i2cdetect.go)
    │        └── list /dev/i2c-* + scan one bus via `i2cdetect -y -r`
    │
    ▼  loop back to LLM call with tool result appended
    ▼  (max_tool_iterations = 20)
    │
    ▼  when LLM returns no tool_calls:
    │
AgentLoop publishes OutboundMessage to bus
    ▼
Channel adapter sends message back to user
```

### Path B — Direct (`make qclaw-direct`)

The direct path is a native Go feature introduced after the `qclaw-llamaCLI` track replaced the retired `llama-server`. It is implemented as the `direct` subcommand in `cmd/qclaw/internal/agent/direct.go`, which calls `ProcessDirectSingleTurn` in `pkg/agent/loop.go`.

```
User types question (terminal only)
    │
    ▼
cmd/qclaw/internal/agent/direct.go  ← `qclaw direct` / `make qclaw-direct`
    │
    ▼
ProcessDirectSingleTurn()  (pkg/agent/loop.go)
    │ Skips the agentic loop and all tool definitions
    │ Applies the same 23-rule pre-router (PreloadSkillsForMessage)
    │ Builds the system prompt (SOUL.md + STOP preamble + skills index)
    │   — no tool schema appended
    ▼
llamaserver.Provider.Chat()  (pkg/providers/llamaserver/provider.go)
    │ Reuses Path A's persistent llama-server child if one is already up
    │ for this engine; otherwise spawns + health-checks it first
    │ Single HTTP POST to /v1/chat/completions, no tools array — plain text
    ▼
Single response printed to terminal → process exits → server is killed
```

The direct path **cannot** compile, upload, or call any tool — sketches come back as text. Its advantage: no tool-schema overhead (~1,800 chars saved from the system prompt) and no multi-iteration loop overhead, yielding ~33% lower latency on factual prompts vs. the agentic path at 0.8B scale.

### Path C — TUI Chat (`make qclaw-tui`)

The TUI (`cmd/qclaw-launcher-tui`) is a full-screen channel-configuration panel that also embeds an interactive chat surface. Unlike Paths A and B, it **pre-warms the llama-server at launch** rather than on the first message.

```
TUI starts (make qclaw-tui)
    │
    ▼
appState.triggerPrewarm()                          (cmd/qclaw-launcher-tui/internal/ui/app.go)
    │  Runs in a background goroutine immediately
    │  newChatPage() → providers.CreateProvider() → llamaserver.Provider
    │  Provider.WarmUp(rootCtx, model) → ensureServer() → spawns llama-server child
    │  Polls /health until 200 OK → marks initialized=true
    │  chatPage stored in appState.prewarm (atomic.Pointer[chatPage])
    │
    ▼
User opens Chat menu item
    │
    ▼
appState.openChat()
    │  Swaps the pre-warmed chatPage out of appState.prewarm atomically
    │  If engine key unchanged: reuse the pre-warmed page (server already running)
    │  If engine changed since pre-warm: discard stale page, create fresh
    │
    ▼
chatPage (Direct or Agentic mode, switchable with F2)
    │
    ├─ Direct mode  → ProcessDirectSingleTurnStream(ctx, text, sessionKey, onToken)
    │    Pre-router runs, single LLM call, tokens streamed live to the output pane.
    │    Session key: "tui:direct:N" (N = toggleCtr, resets on mode switch)
    │
    └─ Agentic mode → ProcessAgenticWithProgressStream(ctx, text, sessionKey, onProgress, onToken)
         Full tool loop. Tool events (⚙ start / ✓ done / ✗ error) shown inline.
         Session key: "tui:agentic:N"

User presses Esc
    │
    ▼
chatPage.close()
    │  cp.cancel() — cancels in-flight LLM request context
    │  goroutine: loop.Close() → Provider.Close() → kills child + cmd.Wait()
    │  After child exits: go triggerPrewarm() — starts fresh pre-warm for next open
    │
    ▼
Back to main menu (server cycling in background)
```

**Pre-warm / stale-page logic:**
- `appState.prewarm` is an `atomic.Pointer[chatPage]` — always written/read via `Store`/`Swap`.
- `openChat()` matches `pre.engineKey` against the current `agents.defaults.model`. Stale pages are shut down in a goroutine.
- On TUI exit, any unclaimed pre-warmed page is shut down before `Run()` returns.

**Mutual exclusion:** Chat and Gateway cannot run simultaneously. The Chat menu item is disabled while the gateway is running, and Start Gateway is disabled while a chat page is open.

### End-to-End Timing Budget

**QClaw-v2 `llamaserver` track — pwm_pins prompt, cold (Run 7):**

| Engine | Wall (cold) | Response | Backend |
|---|---|---|---|
| `yzma` ⭐ baseline | **11m49.6s** | ✅ 241 chars | CPU ARMv8.0 (b9127) |
| `yzma` + study-bible flags | 12m43.2s | ✅ 146 chars | CPU ARMv8.0 |

On the persistent-server architecture, all cold wall time is paid on the **first** call; follow-up turns within the same QClaw process skip the model-load entirely (only prefill of the new turn + decode). Full per-run write-ups: `docs/benchmarks/run7/`, `docs/benchmarks/BENCHMARK_SUMMARY.md`.

**Legacy `qclaw-llmaCLI-v3` track (subprocess per `Chat()`, kept here as a reference):**

Walltimes from Agentic and Direct evaluations on Qwen_Qwen3.5-0.8B-Q4_0 at t=0.3. These are full cold-prefill + decode times paid **on every turn** in the old architecture, because the subprocess driver re-mmap'd the GGUF on every `Chat()`:

| Prompt | Agentic | Direct | Notes |
|---|---|---|---|
| Factual ("PWM pins?") | ~7 min | **~7.4 min** | Both single-iteration; comparable |
| Concept ("MPU vs MCU?") | ~8 min | **~5.5 min** | Direct wins on pure retrieval |
| Voltage safety ("5V on A0?") | ~10 min | **~9.5 min** | Direct slightly faster |
| Short sketch (blink) | ~10 min | **~6 min** | Direct ~40% faster |
| Full sketch (breathe) | ~13 min | **~11 min** | Direct ~15% faster |
| Sketch + compile + flash (LED matrix) | **~20 min** ✅ (with flash) | ~13 min ❌ (text only) | Only agentic can actually flash the board |

**Aggregate (9 prompts, 0.8B, legacy track):** Agentic averages ~12 min/cell with compile+upload capability; Direct averages ~10 min/cell with text-only output. Direct is ~33% faster on factual prompts — the tool-schema savings (~1,800 chars) reduce prefill time noticeably on the Cortex-A53. On the LED-matrix and compile_blink prompts, the agent loop's response-format scaffolding matters — agentic produces better structured output even before the tool call. On the QClaw-v2 `llamaserver` track, this turn-over-turn savings is dwarfed by the cold-start savings (one cold load instead of N).

---

## Part 4: Code Paths for User Questions

### Path 1: Simple Sketch Request (agentic path with tool dispatch)

**User:** "Use the arduino tool to upload a blink sketch for pin 13 with 500 ms toggles."

1. Pre-router fires the `blink` rule → inlines `sketch-patterns/SKILL.md` + `blink.md` (~3.8K chars).
2. Pre-router also fires the `compile/upload` rule → inlines `upload.md` (which contains the directive: "Call `arduino` directly. Do NOT call `read_file` first.").
3. LLM iteration 1 → emits `tool_calls=[arduino({action:"upload", sketch:"..."})]`.
4. Arduino tool compiles via `arduino-cli compile --fqbn arduino:zephyr:unoq --export-binaries`.
5. Arduino tool flashes the resulting `.elf-zsk.bin` to `0x8100000` via OpenOCD.
6. Tool returns `"Sketch compiled and flashed to the board."` — LLM iteration 2 returns final confirmation to the user.

```cpp
// Runs on the STM32U585 MCU
void setup() {
  pinMode(13, OUTPUT);
}

void loop() {
  digitalWrite(13, HIGH);
  delay(500);
  digitalWrite(13, LOW);
  delay(500);
}
```

**Prompt specificity note:** At 0.8B scale, ambient prompts like "blink pin 13 every 500ms" sometimes produce the sketch in markdown without firing the `arduino` tool. Directive prompts naming the tool ("Use the arduino tool to...") raise tool-call reliability to ~100%. This is documented in `docs/QClaw/whitepaper.md` Demo 2.

### Path 1b: LED Matrix Scroll (the canonical agentic demo)

**User:** "Use the arduino tool to upload a sketch that scrolls 'QClaw' across the Uno Q's LED matrix."

1. Pre-router fires the `led-matrix` rule → inlines `led-matrix/SKILL.md` + `scroll-text.md` (~7K chars).
2. Pre-router also fires the `compile/upload` rule → inlines `sketch-patterns/upload.md`.
3. LLM iteration 1 → emits `arduino({action:"upload", sketch:<canonical scroll-text template>})`.
4. Arduino tool compiles (~30s) then flashes via OpenOCD (~3s) to `0x8100000`.
5. LED matrix begins scrolling "QClaw" in blue within a few seconds of the flash completing.

This is the end-to-end demonstration verified twice in v3 (Demo 2 + Demo 3).

### Path 2: Analog Sensor Read

**User:** "Read a potentiometer on A0 and print the value"

Key difference from classic Uno: `analogRead(A0)` reads 0–3.3 V (not 0–5 V). The return value is still 0–1023 in Arduino-compatible mode (mapped from 12-bit to 10-bit internally).

```cpp
// Runs on the STM32U585 MCU
void setup() {
  Serial.begin(9600);  // USART1 on D0/D1
}

void loop() {
  int raw = analogRead(A0);          // 0-1023
  float voltage = raw * (3.3 / 1023.0);  // 0.0 - 3.3 V
  Serial.print("ADC: ");
  Serial.print(raw);
  Serial.print("  Voltage: ");
  Serial.println(voltage);
  delay(200);
}
```

### Path 3: I2C Sensor

Two I2C buses are available for users:

| Bus | Pins | `Wire` object | Use case |
|-----|------|--------------|----------|
| I2C2 | D20 (SDA), D21 (SCL) | `Wire` | Standard, use with any breakout |
| I2C3 | A4 (SDA), A5 (SCL) | `Wire1` | Same pins as classic Uno |
| I2C4 | Qwiic connector | (via Qwiic) | Plug-and-play Modulino ecosystem |

```cpp
// Runs on the STM32U585 MCU — I2C2 bus (D20/D21)
#include <Wire.h>

void setup() {
  Serial.begin(9600);
  Wire.begin();  // I2C2: SDA=D20, SCL=D21
}

void loop() {
  Wire.requestFrom(0x68, 6);  // e.g., MPU-6050 address
  while (Wire.available()) {
    byte b = Wire.read();
    Serial.print(b, HEX);
    Serial.print(" ");
  }
  Serial.println();
  delay(500);
}
```

### Path 4: Python + Bridge (Linux + MCU Together)

For projects that combine Linux AI/processing with MCU hardware control, the Bridge API connects both sides.

**Python (runs on Linux/MPU):**
```python
# Runs on the QRB2210 Linux side
from arduino_alvik import ArduinoAlvik  # or appropriate Bridge library

alvik = ArduinoAlvik.get_instance()
alvik.begin()

sensor_value = alvik.get_distance()  # calls MCU to read sensor via Bridge
print(f"Distance: {sensor_value} cm")
```

**Arduino sketch (runs on STM32U585 MCU):**
```cpp
// Runs on the STM32U585 MCU — exposes a service via Bridge
#include <Arduino_AlvikCarrier.h>

ArduinoAlvikCarrier carrier;

void setup() {
  carrier.begin();
}

void loop() {
  carrier.update();
}
```

### Path 5: PWM (Fade / Motor Speed)

PWM is only available on pins with a tilde: **D3, D5, D6, D9, D10, D11**.

```cpp
// Runs on STM32U585 MCU
// Breathing LED on D9 (TIM4_CH4)
void setup() {
  // no pinMode needed for analogWrite
}

void loop() {
  for (int i = 0; i <= 255; i++) {
    analogWrite(9, i);
    delay(8);
  }
  for (int i = 255; i >= 0; i--) {
    analogWrite(9, i);
    delay(8);
  }
}
```

---

## Part 5: Hardware Acceleration on the MPU

This section is for Linux-side programs running alongside QClaw.

### Adreno 702 GPU (current — graphics + hardware codecs)

On the Uno Q the Adreno 702 is used for graphics (OpenGL/Vulkan) and hardware video codecs surfaced through V4L2 (see "Video Codecs" below). The QClaw inference path on the Uno Q runs on the four Cortex-A53 cores; GPU offload for LLM prefill is not part of the current Uno Q surface.

| API | Version | Use case on Uno Q |
|-----|---------|-------------------|
| OpenGL | 3.1 | 3D rendering |
| OpenGL ES | 3.1 | Embedded graphics |
| Vulkan | 1.0.318 | Low-level GPU |
| OpenCL | 2.0 | GPGPU compute |

### Ventuno Q GPU/NPU (planned)

The Arduino Ventuno Q (Qualcomm Dragonwing IQ-8275) brings two new compute units that QClaw is forward-compatible with:

| Unit | Spec | Planned QClaw use |
|---|---|---|
| Adreno GPU | Vulkan 1.3 / OpenCL 3.0, paired with 16 GB LPDDR5 | LLM prefill offload via llama.cpp Vulkan or OpenCL backend — directly addresses the cold-prefill latency observed on the Uno Q's ~20K-char pre-router-expanded system prompt |
| Hexagon Tensor Processor (NPU) | 40 TOPS INT8 | LLM decode acceleration via QNN/llama.cpp Hexagon backend — targets 3B–7B-class models at interactive speed |
| LPDDR5 | 4× the Uno Q's LPDDR4X bandwidth | Lifts the memory-bandwidth ceiling that bounds decode on the Uno Q today |

The same 23-rule pre-router, 15-skill tree, 8-tool surface, and arduino tool run unchanged on the Ventuno Q with the model and backend swapped underneath.

### Video Codecs (V4L2)

Hardware H.264/H.265 encode/decode via `/dev/video0` and `/dev/video1`. Useful for camera-based projects.

```bash
# GStreamer H.264 decode example
gst-launch-1.0 filesrc location=video.mp4 \
  ! qtdemux ! queue ! h264parse ! v4l2h264dec \
  ! videoconvert ! autovideosink
```

### RGB LEDs via Linux sysfs

The two MPU-controlled RGB LEDs are accessible from Python without any sketch:

```python
# Runs on Linux — no MCU sketch needed
import time

def set_led(color, value):
    with open(f'/sys/class/leds/{color}/brightness', 'w') as f:
        f.write(str(value))

# Blink red:user LED
while True:
    set_led('red:user', 255)
    time.sleep(0.5)
    set_led('red:user', 0)
    time.sleep(0.5)
```

---

## Part 6: What QClaw Can and Cannot Do

The capability matrix depends on which execution path is active.

**Path summary:**

| | Path A — Agentic | Path B — Direct | Path C — TUI Chat |
|---|---|---|---|
| Make target | `make qclaw-agentic` | `make qclaw-direct` | `make qclaw-tui` |
| LLM calls | Multi-iteration loop | Single call | Single call (Direct) / Loop (Agentic) |
| Tools | ✅ 8 tools | ✗ | ✅ when in Agentic mode |
| Streaming | ✅ (agentic tools + final) | ✗ | ✅ token-by-token |
| Server start | On first message | On first message | **At TUI launch** |
| Session key | per channel/user | CLI flag | `"tui:direct:N"` / `"tui:agentic:N"` |
| Telegram | ✅ gateway | ✗ | ✗ |

### Agentic path (`make qclaw-agentic`)

| Capability | How |
|-----------|-----|
| Generates Arduino sketches | LLM text generation, with pre-router-loaded canonical templates |
| **Compiles sketches in-chat** | `arduino` tool → `arduino-cli compile --fqbn arduino:zephyr:unoq` |
| **Uploads sketches to the MCU** | `arduino` tool → OpenOCD flash at `0x8100000` via linuxgpiod (no SSH) |
| **Detects connected boards** | `arduino` tool → `arduino-cli board list` |
| **Captures camera frames** | `camera` tool → `gst-launch-1.0 v4l2src ! videoconvert ! jpegenc ! filesink` |
| **Drives MPU RGB LEDs** | `sysfs_led` tool → writes `/sys/class/leds/<name>/brightness` with active-low inversion |
| **Reports network state** | `network` tool → hostname + interfaces + default gateway, read-only |
| **Scans Linux I²C buses** | `i2cdetect` tool → list `/dev/i2c-*` and `i2cdetect -y -r <bus>` |
| Debugs Arduino errors | User pastes error, QClaw explains and corrects |
| Explains hardware concepts | LLM answers; pre-router inlines the right skill content on relevant queries (15 skills covered) |
| Reads/writes files in workspace | `read_file`, `write_file`, `list_dir` tools |
| Telegram channel | Gateway routes Telegram messages to the agent loop |
| Remembers conversation | Session history in `~/.qclaw/workspace/sessions/` |

### Direct path (`make qclaw-direct`)

Native Go implementation — `ProcessDirectSingleTurn` in `pkg/agent/loop.go`, `direct` subcommand in `cmd/qclaw/internal/agent/direct.go`.

| Capability | How |
|-----------|-----|
| Generates Arduino sketches | LLM text generation, with pre-router-loaded canonical templates (returned as text — user copies into the Arduino IDE or App Lab) |
| Explains hardware concepts | Same 23 pre-router rules as agentic, covering all 15 skills; returns the answer directly |
| Bridge / wireless / vision / audio / Modulino patterns | Pre-router inlines the relevant skill content; the model returns example code and explanations |
| Fast factual Q&A | Single LLM call, no tool round-trips; ~33% lower latency on factual prompts — tool-schema overhead (~1,800 chars) eliminated |

### What QClaw Cannot Do (either path)

| Limitation | Reason |
|-----------|--------|
| Directly control MCU GPIO from Linux | MCU GPIO is controlled by STM32U585; Linux can only call MCU via Bridge |
| Run faster than ~8 tok/s decode (0.8B) | Bounded by LPDDR4X memory bandwidth on QRB2210 |
| Access the internet | Designed for offline-only use; web tools disabled in v3 config |
| Compile/upload sketches in **direct** mode | Direct path has no `arduino` tool — use agentic mode for compile/upload |

### Tools NOT in v3 (disabled to trim per-prompt context)

The v3 config (`config/qclaw.config.json`) disables these tools that were available in v2:

| Tool | Reason for v3 removal |
|------|----------------------|
| `exec` | Security risk; scope doesn't need shell |
| `i2c` | Hardware-specific; ~400 chars of tool schema saved |
| `spi` | Hardware-specific; ~400 chars of tool schema saved |
| `message` | Inter-agent messaging; not used in context |
| `edit_file` | Redundant with `write_file` for sketch use cases |

v3 has gone through two phases of tool surface adjustment:

| Stage | Tools | Schema overhead | Rationale |
|---|---|---|---|
| v2 | 9 (general `exec`, `i2c`, `spi`, `message`, `edit_file`, …) | ~3,400 chars | Permissive but couldn't compile to Uno Q |
| v3 initial (Run 7) | 4 narrow (read/write/list + arduino) | ~1,800 chars | Trimmed to free context for pre-router |
| v3 after Waves 1-3 | 8 narrow (+ camera, sysfs_led, network, i2cdetect) | ~3,400 chars | Restored capability coverage without re-enabling broad-scope tools; each new tool validates inputs against allow-lists rather than accepting arbitrary shell |

The current 8-tool surface matches v2's schema cost but covers a different (and broader) capability surface — camera capture, Linux LED control, network introspection, and I²C bus discovery — none of which v2's general `exec` tool exposed in a structurally safe way.

### Note on the I2C Tool (history)

Earlier QClaw versions registered an `i2c` tool in `pkg/tools/i2c.go` that accessed Linux I2C buses via `/dev/i2c-*`. On the Uno Q those are the **MPU's 1.8 V I2C lines** (on JMISC/JMEDIA) — separate from the MCU's 3.3 V I2C2/I2C3 buses on the Arduino headers. v3 disables this tool by default; sensors wired to the Arduino headers are read from MCU sketches via `Wire`. If you need MPU-side I2C access, re-enable `i2c` in `config.json` and accept the ~400-char tool-schema cost.

---

## Part 7: Configuration Reference (QClaw-v2)

### `pkg/providers/llamaserver` — the persistent on-device provider

The QClaw-v2 inference path is `pkg/providers/llamaserver`. It owns the lifecycle of one `llama-server` child process per configured engine, exposes an `openai_compat` proxy to the agent loop, and is wired into the agent factory by the `llama-server` / `llamaserver` protocol string in `model_list[]`.

**Provider options** (`pkg/providers/llamaserver/provider.go`):

| Option | Default | What it does |
|---|---|---|
| `WithModelsDir(string)` | `~/models` | Resolves the `model` config field against this root |
| `WithThreads(int)` | 4 | `-t` flag — Cortex-A53 cores assigned to the server |
| `WithContextSize(int)` | 4096 | `-c` flag — KV cache budget in tokens |
| `WithParallel(int)` | **1** | `-np` flag — KV slots. Pinned to 1 so the full ctx belongs to the single in-flight request (auto picks ≥2 on b9127+ and divides ctx per slot, causing surprise HTTP 500 `"Context size has been exceeded"` errors) |
| `WithPort(int)` | 8080 | Loopback listener port — must be unique per engine entry to allow simultaneous engines |
| `WithLibraryPath(string)` | `""` | Prepended to `LD_LIBRARY_PATH` when spawning the server. Required for dynamically-linked builds (yzma) whose `.so` files live next to the binary instead of a system path |
| `WithExtraArgs([]string)` | `[]` | Verbatim string slice appended to the spawn command. The per-engine tuning escape hatch — any new llama-server flag can be added without a Go change |
| `WithTimeout(time.Duration)` | 20 min | Cold-prefill budget on the underlying HTTP client. Set via `request_timeout` (seconds) in the model_list entry |

**Lifecycle:** The first `Chat()`, `ChatStream()`, or `WarmUp()` call to a given engine triggers `ensureServer()`, which `exec.Command`s the binary with the pinned + extra flags, polls `/health` until 200 OK, and marks the provider initialized. Every subsequent call POSTs to `127.0.0.1:<port>/v1/chat/completions` with no further server cost. The child is killed when `Provider.Close()` is called (TUI chat page close, or process exit via gateway shutdown hook).

**`WarmUp(ctx, model)`** — added for the TUI pre-warm path. Calls `ensureServer` without making an LLM request. Used by `chatPage.preWarm()` in `cmd/qclaw-launcher-tui/internal/ui/chat.go` to start the server at TUI launch rather than on the first message.

### `config/qclaw.config.json` — the multi-engine `model_list`

```jsonc
{
  "agents": {
    "defaults": {
      "model_name": "yzma",          // ⭐ default engine — change to switch
      "max_tokens": 2048,
      "temperature": 0.3,
      "max_tool_iterations": 8
    }
  },
  "model_list": [
    { "model_name": "yzma",         /* see below */ }
  ]
}
```

**Engine entry shape (yzma, canonical example):**

```jsonc
{
  "model_name":       "yzma",
  "model":            "llama-server/Qwen_Qwen3.5-0.8B-Q4_0.gguf",
  "api_base":         "engines/yzma/lib/llama-server", // binary path (relative resolves from CWD = repo root)
  "api_key":          "local",
  "request_timeout":  1200,                            // → WithTimeout (seconds)
  "extra_body": {
    "models_dir":  "~/models",                         // → WithModelsDir
    "threads":     4,                                  // → WithThreads
    "ctx_size":    9000,                               // → WithContextSize
    "parallel":    1,                                  // → WithParallel
    "port":        8083,                               // → WithPort
    "lib_path":    "engines/yzma/lib",                 // → WithLibraryPath
    "extra_args": [                                    // → WithExtraArgs (verbatim)
      "--flash-attn", "on",
      "--mlock",
      "--cache-type-k", "q8_0",
      "--cache-type-v", "q8_0",
      "--reasoning-budget", "800",
      "--repeat-penalty", "1.1",
      "--repeat-last-n", "64"
    ]
  }
}
```

The factory wiring lives in `pkg/providers/factory_provider.go` under the `llama-server` / `llamaserver` case.

### Server flags pinned by the provider

These are always injected and not configurable:

```
-m <modelPath>  --host 127.0.0.1  --port <port>
-t <threads>    -c <ctxSize>      -np <parallel>
--reasoning off  --jinja  --log-disable
```

- `--reasoning off` — backup for `/no_think` in SOUL.md (suppresses `<think>` preamble)
- `--jinja` — required for chat-template-based tool calling
- `--log-disable` — keeps stdout clean for the parent process

Then any `extra_args` from config are appended.

### Recommended `extra_args` — study-bible optimization pass

| Flag | Effect | Notes |
|---|---|---|
| `--flash-attn on` | Fused QK·softmax·V kernel — ~10% theoretical speedup | No ARMv8.0 fast-path; modest in practice |
| `--mlock` | Pin model weights in RAM (no swap, no eviction) | Pays full pinning cost up front on cold runs |
| `--cache-type-k q8_0` / `-v q8_0` | Quantize KV cache to int8 — halves KV RAM vs fp16 | Mild per-token quant overhead |
| `--reasoning-budget 800` | Cap `<think>` tokens | Belt-and-braces with `/no_think` in SOUL.md |
| `--repeat-penalty 1.1` | Penalize repeated tokens | Reduces output loops on small models |
| `--repeat-last-n 64` | Repeat-penalty lookback window | 64-token window |

**Caveat from Run 7:** these flags add a **53 s cold regression** on yzma (12m43.2s vs 11m49.6s baseline). `--mlock` and `--flash-attn on` pay upfront costs not recouped in a single cold call. They are better candidates for a warm steady-state on a long-lived `qclaw gateway` process. See `docs/QClaw/v2/benchmarks/run7/yzma-optimized-benchmark.md`.

### Engine catalog

| Engine | `api_base` | `lib_path` | Port | Model | Backend | Status |
|---|---|---|---|---|---|---|
| `yzma` ⭐ | `engines/yzma/lib/llama-server` | `engines/yzma/lib` | 8083 | Q4_0 | CPU ARMv8.0 | ✅ Default |
| `yzma-q4kxl` | `engines/yzma/lib/llama-server` | `engines/yzma/lib` | 8084 | Q4_K_XL | CPU ARMv8.0 | Higher quality |
| `yzma-q8` | `engines/yzma/lib/llama-server` | `engines/yzma/lib` | 8085 | Q8_0 | CPU ARMv8.0 | Highest fidelity |

Distinct ports allow running multiple engines simultaneously (e.g. for an A/B benchmark). To switch the default, change `agents.defaults.model_name`. To use a non-default engine for a single call: `qclaw direct --model <name> -m "..."`.

### Other agent defaults

| Parameter | Value | Why |
|---|---|---|
| `max_tokens` | 2048 | Bounds max response length |
| `temperature` | 0.3 | Slight nondeterminism for quality on this small model |
| `max_tool_iterations` | 8 | Most workflows finish in 2–5 iterations |
| `summarize_message_threshold` | 10 | Compress history at 10 messages |
| `arduino` tool | enabled, FQBN `arduino:zephyr:unoq` | Compile + flash sketches |
| `read_file`, `write_file`, `list_dir`, `camera`, `sysfs_led`, `network`, `i2cdetect` | enabled | The 8-tool surface |
| `exec`, `i2c`, `spi`, `message`, `edit_file` | **disabled** | Trimmed to reduce schema overhead |
| Web tools, heartbeat | disabled | Offline-only, no background pings |

### Adding a new engine

No Go changes required for a new llama-server build:

1. Drop the binary somewhere reachable (often a new `engines/<name>/` directory or a submodule).
2. Add a new entry to `model_list[]` in both `config/qclaw.config.json` (committed) and `~/.qclaw/config.json` (runtime) with a unique `model_name` and `port`.
3. Set `api_base` to the binary path, `lib_path` to its `.so` directory (if dynamically linked), and any per-engine `extra_args`.
4. Switch the default with `agents.defaults.model_name`, or invoke directly via `--model <name>`.

The full design rationale is in `docs/QClaw/v2/multi-engine-llamaserver-plan.md`.

### SOUL.md System Prompt Flow (v3)

```
ContextBuilder.BuildMessages() in pkg/agent/context.go
│
├── getIdentity()                ← hardcoded qclaw identity block
│
├── LoadBootstrapFiles()         ← reads from ~/.qclaw/workspace/:
│   ├── AGENTS.md                (if exists)
│   ├── SOUL.md                  ← QClaw Arduino persona + minimal rules
│   ├── USER.md                  (if exists)
│   └── IDENTITY.md              ← QClaw name/purpose
│
├── BuildSkillsSummary()         ← <skills> XML index of workspace/skills/*
│                                  (always emitted in v3 — skills are real)
│
├── PreloadSkillsForMessage()    ← v3 pre-router (skill_preload.go)
│    │                            Runs PER-MESSAGE (not cached). Scans the
│    │                            user message against 23 regex rules covering
│    │                            15 skills. For each match: inlines SKILL.md
│    │                            + listed references into a STOP preamble.
│    │
│    │  Sketch-side (MCU):
│    ├── breathe/fade            → sketch-patterns + breathing.md
│    ├── blink/flash             → sketch-patterns + blink.md
│    ├── button/INPUT_PULLUP     → sketch-patterns + button.md
│    ├── pot/analogRead          → sketch-patterns + potentiometer.md
│    ├── servo/sweep             → sketch-patterns + servo.md
│    ├── sketch/setup()/loop()   → sketch-patterns (SKILL.md only)
│    ├── compile/upload/flash    → sketch-patterns + upload.md
│    ├── CAN bus / FDCAN / OBD   → sketch-patterns + can.md          [Wave 3]
│    ├── DAC / sine wave / tone  → sketch-patterns + dac.md          [Wave 3]
│    ├── OpAmp / OPAMP2 / PGA    → sketch-patterns + opamp.md        [Wave 3]
│    │
│    │  Hardware reference (MPU + MCU):
│    ├── matrix/scroll/marquee   → led-matrix + scroll-text.md
│    ├── pin/PWM/D[0-21]         → uno-q-hardware + pinout.md
│    ├── voltage/5V/3.3V         → uno-q-hardware + voltage-safety.md
│    ├── MPU/MCU/STM32           → uno-q-hardware (SKILL.md only)
│    ├── JDIGITAL/JANALOG/Qwiic  → uno-q-hardware + connectors.md    [Wave 1]
│    ├── USB-C/VIN/power         → uno-q-hardware + power.md         [Wave 1]
│    │
│    │  Dual-chip workflow:
│    ├── Bridge / Python+sketch  → bridge + python-side/mcu-side/examples  [Wave 1]
│    ├── App Lab / Brick         → arduino-app-lab + bricks/deploy   [Wave 2]
│    │
│    │  Linux-side capabilities:
│    ├── Wi-Fi / Bluetooth / HTTP → wireless + wifi-setup/bridge-tcp/bluetooth  [Wave 1]
│    ├── camera / V4L2 / OpenCV  → vision + v4l2/gstreamer/opencv    [Wave 2]
│    ├── microphone / audio / voice → audio + mic-record/audio-output  [Wave 2]
│    ├── /sys/class/leds / red:user → linux-led                      [Wave 3]
│    │
│    │  Plug-and-play sensors:
│    └── Modulino*               → modulino                          [Wave 3]
│
└── GetMemoryContext()           ← memory/MEMORY.md (if exists)
```

Rule provenance: rules without a `[Wave N]` tag are from the initial Run 7 / Wave 0 set. Wave 1 added Bridge, Wireless, connectors, power. Wave 2 added vision, audio, App Lab. Wave 3 added CAN/DAC/OpAmp + Modulino + linux-led.

The static portion (identity + SOUL + IDENTITY + skills index) is cached after the first build. The pre-router output is recomputed per message because it depends on the message content. File-mtime checks trigger a rebuild of the static portion if any source file changes — edit `SOUL.md` or any `skills/<name>/SKILL.md` and it takes effect on the next message without restarting the gateway.

**Direct path mirror:** `scripts/qclaw-direct-chat.py` ports the same 11 rules to Python and assembles a minimal system prompt (SOUL.md + pre-router only — no skills XML, no tool schema).

---

## Part 8: User Mental Model

For users who want to understand the system at a high level. The picture depends on which mode the operator is running.

### Agentic Mode (`make qclaw`)

```
You type a question (e.g. "upload a blink sketch for D13")
        │
        ▼
QClaw's pre-router scans your question for keywords:
  "blink" + "upload" → quickly grabs the right templates
        │
        ▼
The AI model (Qwen3.5-0.8B-Q4_0) thinks on the board
— no internet needed —
        │
        ▼
QClaw writes an Arduino sketch AND
calls the `arduino` tool by itself
        │
        ▼
arduino-cli compiles the sketch for STM32U585
        │
        ▼
OpenOCD flashes the result to the sketch partition
at address 0x8100000 on the microcontroller
        │
        ▼
The microcontroller runs your sketch — LEDs blink immediately
```

### Direct Mode (`make qclaw-direct`)

```
You type a question (e.g. "which pins do PWM?")
        │
        ▼
QClaw's pre-router scans for keywords:
  "pin" + "PWM" → grabs the pinout reference
        │
        ▼
The AI model answers in a single shot — no tool calls, no loop
        │
        ▼
You read the answer in the terminal
(or copy any sketch by hand into Arduino IDE)
```

### Both modes — the Uno Q does two jobs at once

1. **Linux processor (MPU, the QRB2210):** running QClaw itself — the AI model, the pre-router, the agent loop (in agentic mode), and the optional Telegram gateway. Uses ~1.3 GB of RAM.
2. **Arduino microcontroller (MCU, the STM32U585):** running your sketch. Controls every pin on the headers (digital, PWM, ADC, I2C, SPI), the LED matrix, the on-board RGB LEDs, the buttons.

When the agentic mode "uploads" your sketch, it is sending the compiled binary from the MPU to the MCU over a hardware debug interface (SWD) — the two chips talk over wires on the board itself, no SSH, no network. That is why the MPU needs OpenOCD installed and why the MCU sketch partition lives at the specific address `0x8100000`.

This dual-chip design is why the board needs 4 GB of RAM — the AI model alone uses about 1.3 GB.

---

## Appendix A: Quick Voltage Reference

| Location | Voltage | Tolerates 5V? |
|----------|---------|---------------|
| JDIGITAL pins (D0–D21) | 3.3 V | Some pins yes (digital input mode only) |
| JANALOG A0–A3 (ADC mode) | 3.3 V | **NO — max 3.6 V** |
| JANALOG A4/A5 (I2C mode) | 3.3 V | Pull-ups to 3.3 V only |
| JSPI header (MISO/MOSI/SCK) | 3.3 V | Yes (inputs/open-drain) |
| Qwiic connector | 3.3 V | No |
| JMISC MCU lines | 3.3 V | Some |
| JMISC MPU lines | **1.8 V** | No |
| JCTL | **1.8 V** | No |
| VIN (JANALOG/JMEDIA) | 7–24 V | Power input |
| USB-C VBUS | 5 V | Power input |

## Appendix B: Common User Mistakes

| Mistake | Consequence | Fix |
|---------|-------------|-----|
| Applying 5 V to A0–A5 | Damages STM32U585 ADC | Use voltage divider: 5 V → 10 kΩ → A0 → 20 kΩ → GND |
| Using `delay()` in a sensor loop | Loop freezes during delay, misses events | Use `millis()` for non-blocking timing |
| `analogRead()` expecting 0–5 V range | Wrong readings | Calibrate for 0–3.3 V range |
| Forgetting `pinMode(pin, OUTPUT)` | Pin stays as input, no current output | Add `pinMode()` in `setup()` |
| Using D0/D1 for GPIO while Serial is active | UART conflict | Use other pins for GPIO if Serial is needed |
| Trying to control MCU pins from a Python script | Linux GPIO ≠ MCU GPIO | Use Bridge API to call MCU from Python |
| Writing to pin 13 while SPI is active | SPI SCK is on D13 | Use a different pin for LED when SPI is in use |

## Appendix C: Repository Structure (v3)

```
QClaw/
├── cmd/qclaw/                # CLI entry point (Cobra)
│   └── internal/
│       ├── agent/               # agent command + helpers
│       └── onboard/             # qclaw onboard (embed-FS skills bootstrap)
│           └── workspace/       # ← embedded mirror of /workspace
├── pkg/
│   ├── agent/                   # AgentLoop, ContextBuilder, MemoryStore
│   │   ├── loop.go              # multi-iteration agent loop (resolveScopeKey fix at :783)
│   │   ├── context.go           # system prompt assembly + caching
│   │   └── skill_preload.go     # ← v3 pre-router (11 keyword regex rules)
│   ├── channels/                # Telegram, Discord, Slack, terminal, ...
│   ├── config/                  # Config struct, defaults, migrations
│   ├── providers/               # LLM provider adapters
│   │   ├── llamaserver/         # ⭐ QClaw-v2: persistent on-device llama-server provider
│   │   │   └── provider.go       #   WithLibraryPath, WithParallel, WithExtraArgs, …
│   │   ├── openai_compat/        # HTTP client used by llamaserver + cloud providers
│   │   └── factory_provider.go   # Wires model_list[] → provider instances
│   ├── skills/                  # Skill discovery and loading (BuildSkillsSummary)
│   └── tools/
│       ├── arduino.go           # ← compile + OpenOCD flash @ 0x8100000
│       ├── filesystem.go        # read_file, write_file, list_dir
│       ├── camera.go            # ← V4L2 single-frame capture via GStreamer    [Wave 2]
│       ├── sysfs_led.go         # ← /sys/class/leds/* with active-low handling [Wave 3]
│       ├── network.go           # ← read-only hostname/interfaces/gateway     [Wave 3]
│       ├── i2cdetect.go         # ← list /dev/i2c-* + scan a bus              [Wave 3]
│       ├── i2c.go               # (disabled in v3 config — superseded by i2cdetect)
│       └── spi.go               # (disabled in v3 config)
├── workspace/
│   ├── SOUL.md                  # ← QClaw Arduino persona (edit this)
│   ├── IDENTITY.md              # ← QClaw name/purpose
│   └── skills/                  # ← v3 skill bundles, loaded by pre-router (15 skills)
│       │
│       │   ── Sketch-side (MCU) ──
│       ├── sketch-patterns/     # canonical .ino templates
│       │   ├── SKILL.md
│       │   └── references/
│       │       ├── breathing.md
│       │       ├── blink.md
│       │       ├── button.md
│       │       ├── potentiometer.md
│       │       ├── servo.md
│       │       ├── upload.md
│       │       ├── can.md             [Wave 3]
│       │       ├── dac.md             [Wave 3]
│       │       └── opamp.md           [Wave 3]
│       ├── led-matrix/          # 13×8 blue matrix
│       │   ├── SKILL.md
│       │   └── references/scroll-text.md
│       ├── uno-q-hardware/      # pin tables + voltage + connectors + power
│       │   ├── SKILL.md
│       │   └── references/
│       │       ├── pinout.md
│       │       ├── voltage-safety.md
│       │       ├── connectors.md      [Wave 1]
│       │       └── power.md           [Wave 1]
│       │
│       │   ── Dual-chip workflow ──
│       ├── bridge/                                          [Wave 1]
│       │   ├── SKILL.md
│       │   └── references/{python-side,mcu-side,examples}.md
│       ├── arduino-app-lab/                                 [Wave 2]
│       │   ├── SKILL.md
│       │   └── references/{bricks,deploy}.md
│       │
│       │   ── Linux-side capabilities ──
│       ├── wireless/                                        [Wave 1]
│       │   ├── SKILL.md
│       │   └── references/{wifi-setup,bridge-tcp,bluetooth}.md
│       ├── vision/                                          [Wave 2]
│       │   ├── SKILL.md
│       │   └── references/{v4l2,gstreamer,opencv}.md
│       ├── audio/                                           [Wave 2]
│       │   ├── SKILL.md
│       │   └── references/{mic-record,audio-output}.md
│       ├── linux-led/                                       [Wave 3]
│       │   └── SKILL.md
│       │
│       │   ── Plug-and-play sensors ──
│       └── modulino/                                        [Wave 3]
│           └── SKILL.md
├── cmd/
│   ├── qclaw/                   # CLI binary (agentic gateway + direct subcommand)
│   └── qclaw-launcher-tui/      # Full-screen TUI (make qclaw-tui)
│       └── internal/ui/
│           ├── app.go           #   appState, Run(), triggerPrewarm(), openChat()
│           ├── chat.go          #   chatPage: Direct/Agentic modes, preWarm(), close()
│           ├── style.go         #   tview palette
│           └── …               #   menu, model/channel config pages
├── config/
│   └── qclaw.config.json       # ← Hardware-tuned config for Uno Q
├── scripts/
│   ├── qclaw-launch.sh         # Agentic path launcher (loop + tools)
│   ├── qclaw-launch-direct.sh  # Direct path launcher (pre-router + REPL)
│   ├── qclaw-direct-chat.py    # Legacy direct-path Python REPL (POSTs to a long-lived llama-server)
│   ├── qclaw-onboard.sh        # Interactive setup wizard
│   ├── bench-llamaserver-provider.sh # QClaw-v2 llama-server bench
│   └── arduino-cli-setup.sh     # Installs arduino-cli + arduino:zephyr core
├── engines/                     # On-device inference engines
│   └── yzma/                    # Submodule → hybridgroup/yzma (b9127)
│       └── lib/                 #   ⭐ self-contained: llama-server + .so files (ARMv8.0, no build)
├── docs/QClaw/                 # Guides, whitepapers, evaluation artifacts
│   ├── operator-guide.md
│   ├── user-guide.md
│   ├── development/             # This document, setup walkthrough, etc.
│   └── eval/v3/                 # ← 8 evaluation runs + whitepaper + gap analysis + integration record
│       ├── qclaw-v3-whitepaper.md
│       ├── qclaw-eval-v3-run7.md  # agentic-path evaluation
│       ├── qclaw-eval-v3-run8.md  # direct-path evaluation
│       └── Artifacts/Run [1-8]/    # raw cell transcripts and server logs
└── Makefile                     # make qclaw-agentic, qclaw-direct, ...
```
