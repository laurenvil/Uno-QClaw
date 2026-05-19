# QClaw v3: On-Device Agentic AI for Embedded Systems — Architecture, Evaluation, and Results

**A Technical Whitepaper**
**Branch:** `qclaw-v3` · **Date:** 2026-05-15
**Hardware:** Arduino Uno Q (QRB2210) · **Model:** Qwen3.5-0.8B-Q4_0

---

## Abstract

QClaw is an offline-first AI coding assistant that runs entirely on the Arduino Uno Q — a 4-core ARM Cortex-A53 single-board computer running Debian Linux with a co-located STM32U585 microcontroller. It writes, compiles, and uploads Arduino sketches to the MCU with no cloud dependency. This whitepaper documents the v3 engineering effort: seven evaluation runs that progressively isolated the variables governing response quality, tool-call behavior, and latency on sub-1B quantized language models. The central findings are: (1) a pre-router mechanism that inlines relevant skill documents into the system prompt before the LLM call eliminates the need for multi-step `read_file` tool chains on factual retrieval tasks; (2) a corrected hardware flash path using OpenOCD at address `0x8100000` is required for sketches to execute — the pre-installed flash wrapper targets the wrong address; (3) tool-call behavior at 0.8B scale is highly sensitive to prompt surface — directive prompts naming the tool by name succeed where ambient task descriptions do not.

---

## 1. Introduction

### 1.1 Motivation

Consumer AI assistants require internet access and cloud inference infrastructure. For embedded systems contexts — field deployments, air-gapped lab benches, edge devices, industrial controllers — this creates a hard dependency that fails in offline or restricted-network environments. The Arduino Uno Q, while marketed as an embedded Linux board, carries enough compute (4 × Cortex-A53 @ 2.0 GHz, 4 GB LPDDR4X) to run quantized sub-1B models at interactive speeds.

QClaw's thesis is that the full coding workflow — understand a user's request, write a correct sketch, compile it, flash it to the MCU, and report success — can be executed by a 0.8B quantized model running locally on the board itself. The agent acts as both the LLM orchestrator and the Arduino toolchain driver, with no network dependency after initial setup.

### 1.2 Scope of v3

v3 advances the implementation from a working prototype (v2) to a production-ready system by addressing three classes of problems identified in v2's evaluation:

1. **Context efficiency**: The v2 system prompt was 2,571 tokens, causing the 0.8B model to enter reasoning loops — copying rule lists into `reasoning_content` until the budget was exhausted, then repeating the loop in the content phase.
2. **End-to-end hardware integration**: No prior run successfully compiled and flashed a sketch to the MCU using only the agent's tool-call path. Manual verification was always required.
3. **Evaluation rigor**: The benchmark infrastructure had a session key bug that made inter-run comparisons unreliable, and tool-set size was not controlled across runs.

---

## 2. System Architecture

### 2.1 Hardware Platform

The Arduino Uno Q has a split-processor architecture that is critical to understanding QClaw's design:

**MPU side — Qualcomm QRB2210:**
- 4× ARM Cortex-A53 @ 2.0 GHz
- 4 GB LPDDR4X
- Adreno 702 GPU (OpenCL 2.0)
- Debian Linux, kernel 6.16
- Runs llama.cpp (`llama-server`), the qclaw gateway, and all agent logic

**MCU side — STM32U585:**
- ARM Cortex-M33 @ 160 MHz
- 2 MB Flash (two 1 MB banks)
- Zephyr RTOS + Arduino Core (`arduino:zephyr:unoq`, FQBN)
- Runs user sketches
- Exposes the 13-column × 8-row monochrome blue LED matrix (D27001..D27104)

The MCU is flashed from the MPU via SWD using OpenOCD with the `linuxgpiod` interface — no JTAG probe, no USB, no network. The sketch partition starts at flash address `0x8100000` (bank 2, as defined in `boards.txt` under the `unoq.upload.address` key).

### 2.2 Software Stack

```
User input (terminal / SSH / Telegram)
    │
    ▼
qclaw gateway  (pkg/channels/)
    │
    ▼
AgentLoop  (pkg/agent/loop.go)
    ├── ContextBuilder.PreloadSkillsForMessage()  ← pre-router (v3)
    ├── ContextBuilder.BuildMessages()            ← system prompt assembly
    ├── FallbackChain provider (pkg/providers/)   → llama-server HTTP
    └── ToolRegistry.ExecuteWithContext()
            ├── read_file / write_file / list_dir  (pkg/tools/filesystem.go)
            └── arduino                            (pkg/tools/arduino.go)
                    ├── arduino-cli compile --fqbn arduino:zephyr:unoq
                    └── openocd -f openocd_gpiod.cfg -c "flash write_image ... 0x8100000"
```

**LLM inference:** `llama-server` (llama.cpp b9127) serves an OpenAI-compatible HTTP API at `127.0.0.1:8080/v1`. The qclaw gateway uses the `openai_compat` provider pointed at this endpoint.

**Workspace:** `~/.qclaw/workspace/` contains `SOUL.md` (system prompt), `IDENTITY.md`, and a `skills/` tree that the pre-router reads at request time.

### 2.3 The Skills Framework

Skills are directories under `workspace/skills/<name>/` with a mandatory `SKILL.md` index and optional `references/*.md` files:

```
workspace/skills/
  led-matrix/
    SKILL.md              ← index: when to use, 6 rules, tool_calls JSON example
    references/
      scroll-text.md      ← canonical scrolling-text template
  sketch-patterns/
    SKILL.md              ← scaffold, breathing/blink/button/pot/servo patterns
    references/
      breathing.md
      blink.md
      button.md
      potentiometer.md
      servo.md
      upload.md           ← explicit arduino tool directive (new in v3 Run 7)
  uno-q-hardware/
    SKILL.md              ← pin tables, PWM pins, voltage rules
    references/
      pinout.md
      voltage-safety.md
```

Each `SKILL.md` carries YAML frontmatter with a `description` field (≤1024 chars) that doubles as both a metadata label and a trigger instruction ("Read this before writing any sketch that mentions the LED matrix…").

### 2.4 The Pre-Router

`pkg/agent/skill_preload.go` implements keyword-based skill pre-loading. Before the LLM call, `PreloadSkillsForMessage()` scans the user's message against a table of regex rules. Each matching rule loads its target skill's `SKILL.md` and specified reference files, concatenating them into a STOP preamble prepended to the system prompt:

```
[STOP — DO NOT call read_file for the following paths, they are already loaded]
skills/led-matrix/SKILL.md: ...
skills/led-matrix/references/scroll-text.md: ...
[END STOP]
<SOUL.md content>
```

The preamble explicitly names every loaded path so the model can pattern-match against them and skip redundant `read_file` calls.

Rules in v3 Run 7 (complete set):

| Rule | Triggers | Loads |
|---|---|---|
| LED breathing/fade | breathe, fade, analogWrite, PWM | sketch-patterns, breathing.md |
| Blink | blink, digitalWrite, once per second | sketch-patterns, blink.md |
| Potentiometer | potentiometer, analogRead, A0 | sketch-patterns, pot.md; uno-q-hardware, pinout.md |
| Button | button, INPUT_PULLUP, digitalRead | sketch-patterns, button.md; uno-q-hardware, pinout.md |
| Pin/PWM query | pin, D0–D21, A0–A5, PWM | uno-q-hardware, pinout.md |
| Voltage safety | 5V, voltage, 3.3V | uno-q-hardware, pinout.md, voltage-safety.md |
| Hardware overview | MPU, MCU, processor, architecture | uno-q-hardware (SKILL.md only) |
| Servo | servo, sweep | sketch-patterns, servo.md |
| LED matrix | matrix, scroll, Arduino_LED_Matrix | led-matrix, scroll-text.md |
| Compile/upload | compile, upload, flash, arduino-cli | sketch-patterns, upload.md |

---

## 3. Evaluation Framework

### 3.1 Design Principles

Each run is designed as a controlled experiment that isolates a single variable:

| Run | Variable isolated | Baseline |
|---|---|---|
| Run 1 | Baseline quality (SOUL.md v3, skills framework) | — |
| Run 2 | Pre-router: does inlining skill content help? | Run 1 (no pre-router) |
| Run 3 | Pre-router mechanism analysis | Run 2 |
| Run 4 | Full agent loop + 9 tools | Run 3 (direct API) |
| Run 5 | Direct API + tool chaining (no agent loop) | Run 4 |
| Run 6 | Direct API + pre-router + no tools | Run 5 |
| **Run 7** | **Full loop + pre-router + 4-tool trim + LED matrix** | **Run 6** |

### 3.2 Models

The primary production model:

| Model | File | Params | Quant | Size | Decode rate | Role |
|---|---|---|---|---|---|---|
| Qwen3.5-0.8B-Q4_0 | `Qwen_Qwen3.5-0.8B-Q4_0.gguf` | 752M | Q4_0 | 490 MB | ~8 tok/s | Primary production model |

Server flags (consistent across all runs): `--ctx-size 8192 --parallel 1 --flash-attn on --mlock --cache-type-k q8_0 --cache-type-v q8_0 --reasoning-budget 800`

The `--reasoning-budget 800` cap limits `<think>` token spending. The first line of `SOUL.md` is `/no_think`, which suppresses Qwen3's chain-of-thought entirely in compliant configurations.

### 3.3 Benchmark Prompts

Seven prompts were used across runs 1–6 (the "standard battery"). Run 7 added two new capability prompts:

| Tag | Prompt | Tests |
|---|---|---|
| breathe | "Make the LED on pin 9 breathe — fade in and out smoothly." | analogWrite scaffold, pin lookup |
| blink | "Write a sketch that blinks the built-in LED once per second." | digitalWrite scaffold |
| pot | "Read a potentiometer connected to A0 and print its value to the Serial Monitor." | analogRead, Serial |
| button | "When a button on pin 2 is pressed, turn on the LED on pin 13; otherwise turn it off." | INPUT_PULLUP, digitalRead |
| pwm_pins | "Which pins on the Uno Q can do PWM?" | factual retrieval, no sketch |
| five_volt | "Can I connect a 5V sensor to A0?" | voltage safety, factual retrieval |
| mpu_vs_mcu | "What is the difference between the MPU and the MCU on the Uno Q?" | architecture knowledge |
| **led_matrix** | **"Scroll 'QClaw' across the Uno Q's LED matrix and upload it to the board."** | LED matrix skill, arduino tool |
| **compile_blink** | **"Write a sketch that blinks the built-in LED once per second, then compile and upload it to the board."** | arduino tool call chain |

---

## 4. Run 7: Technical Changes

### 4.1 Phase A — Session Key Fix

**Bug:** `resolveScopeKey()` in `pkg/agent/loop.go` only preserved session keys with an `agent:` prefix. User-supplied `--session <key>` values were silently replaced by the route's default key, making session isolation impossible and rendering multi-run comparisons unreliable.

**Fix:**

```go
// Before (broken)
func resolveScopeKey(route routing.ResolvedRoute, msgSessionKey string) string {
    if strings.HasPrefix(msgSessionKey, sessionKeyAgentPrefix) {
        return msgSessionKey
    }
    return route.SessionKey
}

// After (fixed)
func resolveScopeKey(route routing.ResolvedRoute, msgSessionKey string) string {
    if msgSessionKey != "" {
        return msgSessionKey
    }
    return route.SessionKey
}
```

The constant `sessionKeyAgentPrefix = "agent:"` was removed entirely. Verification: `scope_key=qclaw-v3r7-08b-led_matrix` appears correctly in the agent log for all benchmark cells.

### 4.2 Phase B — Tool Set Trim

The tool surface was reduced from 9 tools to 4:

| Tool | Run 4 | Run 7 | Reason for removal |
|---|---|---|---|
| `read_file` | ✅ | ✅ | Required for skill exploration |
| `write_file` | ✅ | ✅ | Required for sketch persistence |
| `list_dir` | ✅ | ✅ | Required for workspace navigation |
| `arduino` | ✅ | ✅ | Required for compile/upload |
| `exec` | ✅ | ❌ | Security risk; scope doesn't need shell |
| `i2c` | ✅ | ❌ | Hardware-specific; adds ~400 chars to schema |
| `spi` | ✅ | ❌ | Hardware-specific; adds ~400 chars to schema |
| `message` | ✅ | ❌ | Inter-agent; not used in context |
| `edit_file` | ✅ | ❌ | Redundant with write_file for sketch use cases |

**Impact:** Tool schema in the system prompt decreased from ~3,400 characters to ~1,800 — saving approximately 380 tokens per request.

### 4.3 Phase C — LED Matrix Skill + Pre-Router Rules

The `led-matrix` skill was created after a deep dive into the UnoQ-datasheet.pdf and the `arduino:zephyr 0.54.1` library sources. Key corrections made during development:

**Dimension correction:** The matrix is 13 columns × 8 rows (`canvasWidth=13, canvasHeight=8` per `Arduino_LED_Matrix.h`), not 12×8 as initially written. Pixel designators D27001..D27104 (104 pixels = 13×8 confirmed). Color is monochrome **blue** — not red.

**API correction:** The canonical `Basic.ino` example bundled with the core uses the 5-argument form: `matrix.beginText(0, 0, 127, 0, 0)` (x, y, R, G, B). A 3-argument form `matrix.beginText(0, 1, 0xFFFFFF)` exists but is non-canonical and produced by the model's prior training data rather than the actual library examples.

**Final canonical template:**

```cpp
#include "ArduinoGraphics.h"    // must come FIRST
#include "Arduino_LED_Matrix.h"

Arduino_LED_Matrix matrix;

void setup() {
    matrix.begin();
    matrix.textFont(Font_5x7);
    matrix.textScrollSpeed(100);
    matrix.clear();
}

void loop() {
    matrix.beginText(0, 0, 127, 0, 0);
    matrix.print("      QClaw      ");  // space-padded
    matrix.endText(SCROLL_LEFT);
    delay(1000);
}
```

**SKILL.md tool-call directive:** A verbatim `tool_calls` JSON example was embedded in `SKILL.md`:

```json
{
  "name": "arduino",
  "arguments": {
    "action": "upload",
    "sketch": "#include \"ArduinoGraphics.h\"\n..."
  }
}
```

This proved necessary but not sufficient — Demo 2 confirmed the model calls the tool when both the example is present AND the prompt explicitly names the tool.

**upload.md reference:** A new `sketch-patterns/references/upload.md` was created that explicitly instructs: "Call `arduino({action: 'upload', sketch: '...'})` directly. Do NOT call `read_file`, `list_dir`, or `write_file` first."

### 4.4 Phase D — Arduino Tool Flash Path Fix

This is the most consequential bug fixed in v3.

**Root cause:** The pre-installed `/usr/local/bin/arduino-flash` wrapper on the Uno Q hardcodes the flash address `0x80F0000`. This address lies in a reserved area near the end of flash bank 1 (total bank 1: 0x08000000–0x080FFFFF = 1 MB). Sketches written here are never executed by the MCU.

The correct address, per `boards.txt` (`unoq.upload.address`) and the official `variants/arduino_uno_q_stm32u585xx/flash_sketch.cfg`, is `0x8100000` — the start of bank 2, which is the actual sketch execution partition.

**Consequence:** Every prior automated upload attempt silently succeeded (OpenOCD reported no error) but the sketch was written to dead flash. Manual verification was always required, disguising the bug as a "model behavior" problem.

**Fix in `pkg/tools/arduino.go`:**

```go
// When OpenOCD is available (production path on Uno Q), compile with
// --export-binaries then flash directly — avoids SSH credential prompt
// from arduino-cli --upload --protocol network.
useLocalFlash := upload && fileExists("/opt/openocd/bin/openocd")

// In runFlashCommand:
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
```

The `--export-binaries` flag produces a `.elf-zsk.bin` at `build/<fqbn-with-dots>/<sketch>.ino.elf-zsk.bin`, which OpenOCD flashes directly via the linuxgpiod SWD interface. No SSH, no network credentials.

---

## 5. Demo Series

### 5.1 Demo 1 — Ambient Prompt, Pre-Tool Era

**Prompt:** "Scroll 'QClaw' across the Uno Q's LED matrix and upload it to the board."

The model produced a correct sketch (include order, API, padding) but emitted it as markdown prose. It made two exploratory tool calls (`list_dir`, `read_file` on a non-existent file) before giving up on tool use. The arduino tool at this stage still used `arduino-cli --upload --protocol network`, which would have prompted for SSH credentials and failed — so even a correct tool call would have produced no LEDs.

**Lesson:** Two independent failures. Fix the tool first, then fix the prompt.

### 5.2 Demo 2 — Directive Prompt + Strengthened Skill Content

After the arduino tool fix and the SKILL.md `tool_calls` JSON example were added:

**Prompt:** "Use the arduino tool to upload a sketch that scrolls 'QClaw' across the Uno Q's LED matrix."

| Iter | Tool call | Result |
|---|---|---|
| 1 | `read_file("...skills/led-matrix/SKILL.md")` | OK — redundant; content already pre-loaded |
| 2 | `arduino({action:"upload", sketch:<canonical>})` | ✅ Compiled and flashed (31s) |
| 3 | Final reply | "The sketch has been successfully compiled and flashed to the Arduino Uno Q!" |

**The LED matrix scrolled "QClaw" — uploaded by the agent, not by hand.**

The iter 1 `read_file` on a pre-loaded file is a known 0.8B behavior: the model's first instinct is to read the skill before acting, even when the STOP preamble says not to. This costs ~4 minutes of prefill latency per redundant call.

Three fixes were jointly necessary:
1. Arduino tool's flash path (OpenOCD at 0x8100000)
2. Directive prompt naming the tool
3. Verbatim `tool_calls` JSON example in SKILL.md

### 5.3 Demo 3 — Stability Verification

Same prompt as Demo 2, new session key (`run7-led-matrix-demo3`), confirming the session key fix.

| Iter | Tool call | Result |
|---|---|---|
| 1 | `list_dir("/home/arduino/.qclaw/workspace")` | OK — unnecessary |
| 2 | `read_file(".../sketches/scroll-qclaw.ino")` | ❌ not found |
| 3 | `write_file(".../sketches/scroll-qclaw.ino", <canonical sketch>)` | OK (7 ms) |
| 4 | `arduino({action:"upload", sketch:<canonical>})` | ✅ Flashed (33.8s) |
| 5 | Final reply | "The sketch has been successfully uploaded to the Uno Q board!" |

Session key `run7-led-matrix-demo3` appeared correctly in `scope_key=` — Phase A fix confirmed. The 4-step tool scaffold before the arduino call (explore → read-fail → write → upload) is the 0.8B's habitual file-first reasoning pattern at this model size. The eventual outcome was correct; the extra iterations added ~20 minutes of latency.

---

## 6. Benchmark Results (Phase E)

Phase E ran the 2 new capability prompts on the 0.8B model.

| Cell | Wall | Iters | arduino upload | Sketch quality | Verdict |
|---|---|---|---|---|---|
| 08b/led_matrix | 1168s | 1 | 0 | ✅ canonical template correct | Ambient prompt → markdown only |
| 08b/compile_blink | 1339s | 2 | 0 | ❌ println repetition loop | Ambient prompt → text, generation failure |

### 6.1 08b/led_matrix

The pre-router fired correctly, inlining `led-matrix/SKILL.md` and `scroll-text.md` (~7K chars). The model's single-iteration response produced the canonical sketch verbatim — correct include order, `Font_5x7`, 5-arg `beginText(0,0,127,0,0)`, space-padded string, `SCROLL_LEFT` — but delivered it in markdown prose with the preamble "I'll help you create and upload a sketch...". No `arduino` tool call was attempted.

This is the definitive characterization of the ambient-prompt gap: the skill content is inlined correctly, the sketch is correct, but the 0.8B model at t=0.3 does not self-initiate a tool call unless the prompt explicitly names the tool.

### 6.2 08b/compile_blink

Iter 1 called `read_file` on `sketch-patterns/references/blink.md` (the compile/upload pre-router rule fired correctly). Iter 2 produced a sketch response that fell into a `Serial.println` repetition loop — printing the same two status lines dozens of times. This is a known quantized-model failure mode when the prompt contains both a creative task ("write a sketch") and an action directive ("compile and upload") without a clear stopping criterion. No arduino tool call was attempted.

---

## 7. Cross-Run Analysis

### 7.1 What the Pre-Router Solves

Without the pre-router, the model must call `read_file` to load skill content. At 0.8B scale, a `read_file` call costs a full LLM iteration: ~10-20 minutes of latency on cold context (cold prefill) plus the decode time for the response. The pre-router amortizes this cost to zero additional LLM iterations — the skill content is injected before the first call.

The tradeoff is system prompt size: each pre-router hit adds the content of the matched skill files. The led-matrix rule adds ~7K chars (~1,750 tokens). At 0.8B scale, this is acceptable.

### 7.2 The Prompt Specificity Problem

Across all runs, the pattern is consistent: sub-1B models at inference-efficient quantizations do not reliably infer tool invocation from task description alone. They require explicit instruction.

| Prompt type | Tool call rate (0.8B) |
|---|---|
| Task description only ("...and upload it") | 0% in benchmark |
| Directive naming the tool ("Use the arduino tool to...") | ~100% in demos (2 of 2) |

This is not a skill content problem — the SKILL.md `tool_calls` JSON example is present and the model produces a correct sketch. The failure is at the tool-invocation decision point. The model defaults to its pre-training distribution of "helpful explanation" rather than "execute an action."

**Resolution path:** Add a SOUL.md-level instruction: "Any time the user asks to upload, run, flash, or compile a sketch for the board, you MUST call the `arduino` tool with `action='upload'` directly. Do not describe the steps in text." This operates at a higher authority level than skill content.

### 7.3 The Agent Loop's Role

Run 4 (full loop, 9 tools) showed that the 0.8B benefits from the loop's response-format scaffolding but degrades with a large tool surface. The optimal 0.8B configuration is: loop ✅ required, pre-router ✅ required, trimmed tool surface (4 narrow tools at minimum). This yields best sketch quality and reliable tool calls together.

### 7.4 Generation Failures at 0.8B

The compile_blink cell's repetition loop is a known pathology of small quantized models when the prompt spans multiple task types (creative generation + action directive) without a termination cue. Mitigations:

1. **Structural prompts**: "Write a sketch (code block only, no prose) then call the arduino tool." Forces the model into a structured response format that prevents runaway generation.
2. **max_tokens cap**: The current `max_tokens: 2048` is generous; capping at 512 for sketch-only prompts would terminate the repetition loop before it becomes severe.
3. **Temperature**: The 08b benchmark runs at t=0.3, which should suppress creative drift. The repetition loop at t=0.3 suggests the loop is a structural failure mode, not a randomness artifact.

---

## 8. Flash Address: A Root-Cause Analysis

The flash address discrepancy is worth documenting in detail because it affected every automated upload attempt across Runs 1–6.

### 8.1 STM32U585 Flash Layout

The STM32U585 has 2 MB of flash divided into two 1 MB banks:

| Region | Address range | Size | Contents |
|---|---|---|---|
| Bank 1, areas 1–7 | `0x08000000`–`0x080EFFFF` | 960 KB | Zephyr kernel + Arduino core |
| Bank 1, area 8 | `0x080F0000`–`0x080FFFFF` | 64 KB | Reserved / end-of-bank |
| Bank 2 start | `0x08100000` | — | **Sketch partition** |
| Bank 2 remainder | `0x08100000`–`0x081FFFFF` | 1 MB | Sketch code + data |

`/usr/local/bin/arduino-flash` hardcodes `0x80F0000`. This notation is missing a leading zero compared to the full 8-digit STM32 address, but more importantly maps to `0x080F0000` — the reserved 64 KB at the very end of bank 1. A sketch written here does not execute. The MCU's reset vector jumps to the Zephyr boot entry point in bank 1, and Zephyr then chains to the sketch partition at `0x8100000` (bank 2). Without a valid image at `0x8100000`, Zephyr's application launcher finds nothing and the LED matrix never starts.

### 8.2 The Correct Invocation

From `variants/arduino_uno_q_stm32u585xx/flash_sketch.cfg` (the official Zephyr core flash script):

```tcl
flash write_image erase ${filename} 0x8100000 bin
```

the qclaw `runFlashCommand` implementation mirrors this exactly:

```go
const sketchAddress = "0x8100000"
flashCmds := fmt.Sprintf(
    "reset_config srst_only srst_nogate srst_push_pull connect_assert_srst; "+
        "init; reset; halt; flash info 0; "+
        "flash write_image erase %s %s bin; "+
        "reset run; shutdown",
    binPath, sketchAddress,
)
```

### 8.3 Verification

Manual verification was performed before running Demo 2:
1. Compiled `Arduino_LED_Matrix/examples/Basic/Basic.ino` (the official demo sketch)
2. Flashed to `0x8100000` using the corrected invocation
3. User confirmed: "Yes, I can see 'arduino.cc/uno-q' scrolling in blue." ✅

The stock `arduino-flash` wrapper was separately verified to write to `0x80F0000` and produce a silent no-op on the LED matrix.

---

## 9. Open Issues and Future Work

### 9.1 SOUL.md Tool-Call Trigger

The highest-priority gap: the ambient-prompt tool-call failure. The fix requires a SOUL.md-level imperative — a rule that fires before any skill content is considered. Proposed addition (~30 tokens):

```
When the user asks to upload, flash, run, or compile a sketch to the board,
call the `arduino` tool with `action="upload"` and the complete sketch source.
Do not describe the steps in a text reply — use the tool.
```

This should close the gap between directive and ambient prompts for the `led_matrix` and `compile_blink` benchmark cells.

### 9.2 0.8B Repetition Loop Prevention

The `compile_blink` repetition loop warrants investigation. Two experiments:

1. **Structured prompt**: "Write only the sketch source code (no prose). After writing the sketch, call the arduino tool with action=upload."
2. **max_tokens: 512**: Force the model to terminate the sketch quickly, then enter iteration 2 for the tool call.

### 9.3 Ventuno Q GPU/NPU Acceleration (planned)

The Arduino Ventuno Q (Qualcomm Dragonwing IQ-8275, 8-core Kryo Gen 6 ARMv9, Adreno GPU with Vulkan 1.3 / OpenCL 3.0, Hexagon Tensor Processor NPU at 40 TOPS INT8, 16 GB LPDDR5) introduces two acceleration paths QClaw is forward-compatible with:

- **GPU prefill offload** via llama.cpp's Vulkan or OpenCL backend. The Ventuno Q's Adreno is a generation ahead of the Uno Q's Adreno 702, and LPDDR5 lifts the bandwidth ceiling that dominates decode on the Uno Q today. This directly addresses cold-prefill latency on the pre-router-expanded ~20K-char system prompt.
- **NPU decode acceleration** via the Hexagon Tensor Processor. With 40 TOPS INT8 and a QNN/llama.cpp Hexagon backend, the Ventuno Q can support 3B–7B-class models at interactive speed — model scale large enough to close the prompt-specificity gap and the niche-topic quality ceiling observed at 0.8B.

The skills framework, pre-router, 8-tool surface, and arduino tool are forward-compatible — the same agentic/direct paths run unchanged on the Ventuno Q with the model and backend swapped underneath.

---

## 10. Conclusion

v3 delivers the complete coding workflow on the Arduino Uno Q:

1. **Pre-router** eliminates multi-step skill loading for common request patterns, injecting relevant skill content before the first LLM call.
2. **Arduino tool** correctly compiles and flashes sketches to the MCU at `0x8100000` via OpenOCD — no SSH, no credentials, no wrong addresses.
3. **LED matrix skill** provides the canonical scrolling-text template with correct library include order, 5-arg `beginText` API, space padding rules, and an explicit tool-call JSON example.
4. **Session key fix** makes multi-session benchmarks reliable.
5. **Tool set trim** reduces per-prompt schema overhead by ~1,600 characters.

The system has been verified end-to-end: "QClaw" scrolls across the physical LED matrix on an Arduino Uno Q, uploaded autonomously by the agent. The open gap — ambient prompts not triggering tool calls — has a known fix (SOUL.md imperative) ready for Run 8.

---

*All source code lives in the `qclaw-v3` branch of `github.com/laurenvil/QClaw`. Evaluation artifacts are under `docs/QClaw/v3/Artifacts/Run 7/`.*
