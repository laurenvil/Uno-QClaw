<img width="2604" height="1600" alt="QClaw-Branded" src="https://github.com/user-attachments/assets/b9af9bc4-77a6-4321-af4c-b053ff77335a" />

<div align="center">
<pre>
██╗   ██╗ ███╗   ██╗  ██████╗   ██████╗  ██████╗██╗      █████╗ ██╗    ██╗
██║   ██║ ████╗  ██║ ██╔═══██╗ ██╔═══██╗██╔════╝██║     ██╔══██╗██║    ██║
██║   ██║ ██╔██╗ ██║ ██║   ██║ ██║   ██║██║     ██║     ███████║██║ █╗ ██║
██║   ██║ ██║╚██╗██║ ██║   ██║ ██║▄▄ ██║██║     ██║     ██╔══██║██║███╗██║
╚██████╔╝ ██║ ╚████║ ╚██████╔╝ ╚██████╔╝╚██████╗███████╗██║  ██║╚███╔███╔╝
 ╚═════╝  ╚═╝  ╚═══╝  ╚═════╝   ╚══▀▀═╝  ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
</pre>
</div>

# QClaw

**QClaw** is an on-device agentic AI assistant for the Arduino Uno Q. It writes, compiles, and uploads Arduino sketches; captures camera frames; drives Linux-side LEDs; reports network state; and scans I²C buses — all running entirely on the board. No internet. No API keys. No cloud.

Forked from upstream [picoclaw](https://github.com/sipeed/picoclaw) — repo: [Uno-QClaw](https://github.com/laurenvil/Uno-QClaw) · inference via the embedded [`engines/llamacli`](engines/llamacli) submodule (precompiled `assix/Arduino-UnoQ-Optimized-Llama-CLI`) · default model: Qwen3.5-0.8B Q4_0

QClaw ships two execution paths sharing the same model, system prompt, and 15-skill tree:

- **Agentic** — agent loop + 23-rule pre-router + 8 tools. End-to-end compile/flash, camera capture, MPU LED control, network diagnostics, I²C bus scan.
- **Direct** — same 23-rule pre-router + single LLM call, no tools, no loop. Faster Q&A across all 15 skills.

---

## What QClaw Does

| Capability | Path | How |
|---|---|---|
| Generate Arduino sketches | Both | LLM text generation with pre-router-inlined canonical templates |
| Compile sketches | Agentic | `arduino` tool → `arduino-cli compile --fqbn arduino:zephyr:unoq` |
| Upload sketches to the MCU | Agentic | `arduino` tool → OpenOCD flash at `0x8100000` via linuxgpiod (no SSH, no network) |
| Detect connected boards | Agentic | `arduino` tool → `arduino-cli board list` |
| Capture camera frames | Agentic | `camera` tool → GStreamer V4L2 single-frame pipeline |
| Drive MPU RGB LEDs | Agentic | `sysfs_led` tool → `/sys/class/leds/*/brightness` with active-low inversion |
| Report network state | Agentic | `network` tool → hostname, interfaces, default gateway (read-only) |
| Scan Linux I²C buses | Agentic | `i2cdetect` tool → list `/dev/i2c-*`, `i2cdetect -y -r <bus>` |
| Read/write workspace files | Agentic | `read_file`, `write_file`, `list_dir` |
| Answer hardware questions | Both | Pre-router inlines the relevant skill content (15 skills covered) |
| Telegram, terminal, SSH | Agentic | qclaw channel adapters |
| Fully offline | Both | All inference, compilation, and flashing runs locally on the QRB2210 |

---

## Quick Start

```bash
git clone https://github.com/laurenvil/Uno-QClaw.git ~/ArduinoApps/QClaw
cd ~/ArduinoApps/QClaw

# Pull the precompiled llama-cli (mpu/llama-cli aarch64 ELF, ~12 MB)
git submodule update --init --recursive engines/llamacli

# Download the model (~490 MB for Q4_0)
mkdir -p ~/models
wget -O ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf \
  'https://huggingface.co/Qwen/Qwen3.5-0.8B-GGUF/resolve/main/Qwen3.5-0.8B-Q4_0.gguf'

# Build, install arduino-cli, configure (one time)
make qclaw-install

# Start a session
make qclaw-agentic    # full agent loop + 8 tools (compile/upload/camera/sysfs_led/network/i2cdetect)
```

`make qclaw-install` builds the binary, installs the system prompt and 15-skill tree, downloads `arduino-cli`, installs the `arduino:zephyr` board core, and runs the interactive setup wizard. `make qclaw` is an alias for `make qclaw-agentic`. Note that on the `qclaw-llamaCLI` track the *direct* path is disabled — see [Two Execution Paths](#two-execution-paths) below.

---

## Two Execution Paths

Both paths share the same `engines/llamacli` engine, the same `SOUL.md`, and the same 23-rule pre-router. They differ only in what surrounds the LLM call.

| Aspect | `make qclaw-agentic` | `make qclaw-direct` |
|---|---|---|
| Agent loop (multi-iteration) | ✅ | ❌ (single call) |
| Tools available | **8** | None |
| Pre-router | ✅ (23 rules, 15 skills) | ✅ (same 23 rules) |
| Compile sketches | ✅ | ❌ (text-only) |
| Upload to board | ✅ flashes STM32U585 at `0x8100000` via OpenOCD | ❌ |
| Camera frame capture | ✅ via `camera` tool | ❌ |
| MPU LED control | ✅ via `sysfs_led` tool | ❌ |
| Network introspection | ✅ via `network` tool | ❌ |
| I²C bus scan | ✅ via `i2cdetect` tool | ❌ |
| Telegram gateway | ✅ | ❌ (terminal only) |
| Best for | Hardware actions, multi-step workflows | Fast factual Q&A across all 15 skills |

> **Note (qclaw-llamaCLI track):** the direct path's Python REPL (`qclaw-direct-chat.py`) was a thin OpenAI-compatible HTTP client pointed at the now-retired `llama-server`. With the llama-cli provider spawning a subprocess per `Chat()` call there is no HTTP endpoint for it to talk to, so `make qclaw-direct` is disabled on this track ([`scripts/qclaw-launch-direct.sh`](scripts/qclaw-launch-direct.sh) prints a redirect and exits). Use `make qclaw-agentic` for everything.

The agent loop's response-format scaffolding contributes real quality on complex code generation, not just tool-call mechanics. The pre-router alone is necessary but not sufficient for harder prompts at 0.8B scale.

---

## Hardware Target

### Arduino Uno Q (primary)
- **SoC**: Qualcomm Dragonwing QRB2210
- **CPU**: 4× Cortex-A53 @ 2.0 GHz (ARMv8.0)
- **GPU**: Adreno 702 @ 845 MHz — OpenCL 2.0
- **RAM**: 4 GB LPDDR4X
- **OS**: Debian Linux, kernel 6.16
- **MCU**: STM32U585 (Zephyr RTOS + Arduino Core) — where sketches run

### Arduino Ventuno Q (upcoming)
- **SoC**: Qualcomm Dragonwing IQ-8275
- **CPU**: 8-core Kryo Gen 6 (ARMv9)
- **NPU**: Hexagon Tensor Processor, 40 TOPS INT8
- **RAM**: 16 GB LPDDR5

---

## Split-Processor Architecture

QClaw's agentic loop orchestrates the full sketch lifecycle — generate, compile, flash, observe — across the Arduino Uno Q's dual-silicon topology, with the MPU driving the loop and the MCU executing the resulting firmware:

<img width="2816" height="1536" alt="QClaw-Architecture" src="https://github.com/user-attachments/assets/f6adf688-fd3d-4dd0-ba3b-59b933478e47" />

### MPU Side (Qualcomm QRB2210)
- **Processor:** 4 × ARM Cortex-A53 @ 2.0 GHz
- **Operating System:** Debian Linux (kernel 6.16)
- **Role:** Host environment running the `qclaw` agent framework (which spawns the precompiled `engines/llamacli/mpu/llama-cli` as a subprocess per inference call), local compilation toolchain, and debugging suites.

### MCU Side (STM32U585)
- **Processor:** ARM Cortex-M33 @ 160 MHz
- **Operating System:** Zephyr RTOS + Arduino Core (`arduino:zephyr:unoq`)
- **Role:** Real-time physical I/O execution, sensor reading, motor control, and driving the 13 × 8 blue LED matrix.

### Hardware Interconnect
The MPU and MCU do not communicate over standard external interfaces like USB or network cables. Instead, they share:
1. **Serial Bridge (UART/RPC):** For runtime messaging and remote procedure calls.
2. **SWD (Serial Wire Debug) Interface:** Connected directly via MPU GPIO pins using a `linuxgpiod` driver interface. This SWD connection allows the MPU to halt, erase, program, and reset the MCU's flash memory.

See [`docs/QClaw/mcu-communication-whitepaper.md`](docs/QClaw/mcu-communication-whitepaper.md) for the full compile/flash pipeline, the `0x8100000` address fix, and the comparison with Arduino's `remoteocd` utility.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    QClaw (this repo)                          │
│                                                                │
│  Agentic path                                                  │
│  ┌────────────────────────────────────────────────────┐       │
│  │ qclaw agent / gateway (Go)                       │       │
│  │   ├── channels/  (Telegram, terminal, SSH, ...)     │       │
│  │   ├── pre-router (skill_preload.go, 23 rules)       │       │
│  │   ├── agent loop (multi-iter, tool dispatch)        │       │
│  │   └── tools (8):                                    │       │
│  │       • read_file / write_file / list_dir           │       │
│  │       • arduino   → arduino-cli + OpenOCD@0x8100000 │       │
│  │       • camera    → gst-launch-1.0 v4l2src ! ...    │       │
│  │       • sysfs_led → /sys/class/leds/*/brightness    │       │
│  │       • network   → /proc/net/route + interfaces    │       │
│  │       • i2cdetect → /dev/i2c-* + i2cdetect -y -r    │       │
│  └────────────────────────────────────────────────────┘       │
│                                                                │
│  Direct path                                                   │
│  ┌────────────────────────────────────────────────────┐       │
│  │ qclaw-direct-chat.py (DISABLED on qclaw-llamaCLI)   │       │
│  │   was a Python REPL that POSTed to llama-server's   │       │
│  │   /v1/chat/completions; with no server to talk to,  │       │
│  │   the script exits with a redirect to `qclaw-agentic`│      │
│  └────────────────────────────────────────────────────┘       │
│                                                                │
│                                fork+exec per Chat()            │
│  pkg/providers/llamacli ──────►  engines/llamacli/mpu/llama-cli │
│     (Go subprocess driver)         (assix precompiled aarch64)  │
│                                                                │
│  engines/llamacli/  (submodule → assix/Arduino-UnoQ-Optimized-  │
│                      Llama-CLI; ships mpu/llama-cli + llama.cpp │
│                      source unused at runtime)                  │
└──────────────────────────────────────────────────────────────┘
```

The pre-router (`pkg/agent/skill_preload.go`) scans the user message against 23 keyword regex rules spanning 15 skills. Each match inlines the corresponding `SKILL.md` and reference files into the system prompt before the LLM call — the model never has to call `read_file` for known skill content.

| Domain | Skills | Sample triggers |
|---|---|---|
| Sketch fundamentals | `sketch-patterns` | `breathe`, `blink`, `button`, `analogRead`, `servo`, `compile`, `upload`, `CAN bus`, `DAC`, `OPAMP` |
| LED matrix | `led-matrix` | `matrix`, `scroll`, `Arduino_LED_Matrix` |
| Hardware reference | `uno-q-hardware` | `pin`, `5V`, `voltage`, `JDIGITAL`, `Qwiic`, `USB-C`, `VIN` |
| Dual-chip workflow | `bridge`, `arduino-app-lab` | `Bridge`, `Python + sketch`, `App Lab`, `Brick` |
| Linux-side capabilities | `wireless`, `vision`, `audio`, `linux-led` | `Wi-Fi`, `Bluetooth`, `camera`, `OpenCV`, `microphone`, `red:user` |
| Plug-and-play sensors | `modulino` | `Modulino`, `ModulinoDistance` |

The `arduino` tool compiles via `arduino-cli`, then flashes via OpenOCD directly to the STM32U585 sketch partition at `0x8100000`. (The pre-installed `arduino-flash` wrapper hardcodes `0x80F0000`, which lands in a reserved area near the end of bank 1 and never executes — see `docs/QClaw/whitepaper.md` for the root-cause analysis.)

Everything runs locally as a Go subprocess driving the precompiled `mpu/llama-cli` — no HTTP loopback, no persistent server, no port to keep alive across requests.

---

## Benchmarks (Arduino Uno Q)

Model: `Qwen_Qwen3.5-0.8B-Q4_0.gguf` · `-c 2048 -t 4 --temp 0.0 --reasoning off` · subprocess per `Chat()`. See [`docs/GPU/benchmark-results.md`](docs/GPU/benchmark-results.md) for the full V1 benchmark methodology and raw logs.

### Throughput & resource footprint (warm cache)

| Metric | Value |
|---|---|
| Prompt processing (0.8B Q4_0) | **10.6 tok/s** |
| Decode throughput (short ≤ n=64, 0.8B Q4_0) | **8.8 tok/s** |
| Decode throughput (sustained n=128, 0.8B Q4_0) | ~4.8 tok/s |
| 64-tok wall (warm-cache `Chat()`) | 10.34 s |
| Cold-start `Chat()` (mmap GGUF + grammar compile + 1 tok) | 12.17 s |
| Model RAM (0.8B Q4_0, mmap) | ~490 MB |
| Per-`Chat()` `llama-cli` RSS peak | ~1.1 GB (model + KV + grammar tables) |

These numbers replace the older yzma `llama-server` baseline (`pp=5.37 / tg=3.69 t/s` on the same model). The CLI path is roughly **2× faster** end-to-end on warm-cache short interactions thanks to a more recent llama.cpp build (`b9099` vs `9127`) and the elimination of the HTTP round trip and chat-template re-parse. Decode rate at long sequences converges back to the bandwidth-limited ~5 t/s regime that the LPDDR4X imposes on this SoC.

### Per-prompt walltime — Agentic vs Direct

| Prompt | Direct | Agentic | Direct quality | Agentic quality |
|---|---|---|---|---|
| Factual ("which pins do PWM?") | ~7.4 min | ~7 min | ✅ correct | ✅ correct |
| Concept ("MPU vs MCU?") | ~5.5 min | ~8 min | ✅ correct | ✅ correct |
| Voltage safety ("5V on A0?") | ~9.5 min | ~10 min | ✅ correct | ✅ correct |
| Short sketch (blink) | ~6 min | ~10 min | ✅ correct | ✅ correct |
| Full sketch (breathe) | ~11 min | ~13 min | ✅ correct | ✅ correct |
| Sketch + compile + flash (LED matrix) | ~13 min | ~20 min | ❌ text only | ✅ flashes board |

Direct is ~33% faster on pure factual prompts; agentic is required for any prompt that ends in a hardware action.

### Token economy

| Configuration | System prompt size | Tool schema | Per-turn cost |
|---|---|---|---|
| Direct | ~9.5K SOUL + ~7K pre-router | none | ~16K chars |
| Agentic | ~9.5K SOUL + ~7K pre-router + ~3.4K tool schema | 8 tools | ~20K chars |

### Ventuno Q GPU/NPU acceleration (planned)

The upcoming Arduino Ventuno Q (Qualcomm Dragonwing IQ-8275) brings two new compute units to the same QClaw stack:

| Unit | Spec | Planned use |
|---|---|---|
| Adreno GPU (Vulkan 1.3 / OpenCL 3.0) | mobile-class, shared with 16 GB LPDDR5 | Prefill offload via llama.cpp Vulkan/OpenCL backend — eliminates cold-prefill latency on the 20K-char system prompt |
| Hexagon Tensor Processor (NPU) | 40 TOPS INT8 | Quantized-model decode acceleration via QNN/llama.cpp Hexagon backend — targets 3B–7B models at interactive speed |
| LPDDR5 bandwidth | 4× the Uno Q's LPDDR4X | Lifts the decode bandwidth ceiling that bottlenecks the Adreno 702 on the Uno Q today |

QClaw's skills framework, pre-router, and arduino tool are forward-compatible — the same agentic/direct paths run unchanged on the Ventuno Q, with model selection upgraded from 0.8B Q4_0 to a larger NPU-accelerated quantization.

---

## Make Targets

| Command | What it does |
|---|---|
| `make qclaw` | Default — alias for `make qclaw-agentic` |
| `make qclaw-agentic` | Agentic path: agent loop + 23-rule pre-router + 8 tools |
| `make qclaw-direct` | Direct path: pre-router + single LLM call, no tools |
| `make qclaw-install` | Full first-time setup (build + workspace + arduino-cli + wizard) |
| `make qclaw-onboard` | Re-run setup wizard (Telegram token, allow list) |
| `make qclaw-setup` | Reinstall system prompt + skills tree after a git pull |
| `make qclaw-arduino-setup` | Install or update arduino-cli and the Uno Q board core |
| `make qclaw-stop` | Stop background processes |
| `make build` | Build the qclaw binary for current platform |
| `make build-linux-arm64` | Cross-compile for Uno Q (ARM64) |

---

## Repository Layout

```
Uno-QClaw/
├── cmd/qclaw/             # CLI entry point (Cobra)
├── pkg/
│   ├── agent/                # Agent loop, context, pre-router, tool dispatch
│   ├── channels/             # Telegram, terminal, IRC, Matrix, ...
│   ├── providers/            # LLM provider adapters (OpenAI-compat, Anthropic, ...)
│   └── tools/                # arduino, camera, sysfs_led, network, i2cdetect, filesystem
├── engines/llamacli/         # Submodule → assix/Arduino-UnoQ-Optimized-Llama-CLI
│   ├── mpu/llama-cli         #   precompiled aarch64 ELF (assix, llama.cpp b9099)
│   └── llama.cpp/            #   source tree (unused at runtime)
├── config/qclaw.config.json  # Runtime config template
├── workspace/
│   ├── SOUL.md               # System prompt / agent persona
│   ├── IDENTITY.md           # Identity file
│   └── skills/               # Pre-router-loaded skill bundles (15 skills)
├── scripts/
│   ├── qclaw-launch.sh        # Agentic launcher
│   ├── qclaw-launch-direct.sh # Direct launcher
│   ├── qclaw-direct-chat.py   # Direct-path Python REPL
│   ├── qclaw-onboard.sh       # Setup wizard
│   └── arduino-cli-setup.sh   # arduino-cli + arduino:zephyr installer
├── assets/qclaw-logo.svg
├── docs/QClaw/               # Technical references (see below)
└── Makefile
```

---

## Docs

| Document | Description |
|---|---|
| `docs/QClaw/development/setup-walkthrough.md` | Step-by-step from a fresh Uno Q to a running QClaw |
| `docs/QClaw/development/launch-and-debug.md` | Launching and debugging the llama-cli provider end-to-end |
| `docs/QClaw/development/architecture-study-bible.md` | Dual-processor architecture, pin tables, voltage rules, data paths |
| `docs/QClaw/development/UnoQ-datasheet.pdf` | Official Arduino Uno Q hardware datasheet |
| `docs/QClaw/whitepaper.md` | Architecture and evaluation whitepaper |
| `docs/QClaw/capability-integration.md` | Skill, reference, and tool integration record |
| `docs/QClaw/mcu-communication-whitepaper.md` | MPU↔MCU compile/flash pipeline deep dive |
| `docs/GPU/llama-cli-provider-whitepaper.md` | Why and how QClaw swapped yzma `llama-server` for `engines/llamacli` |
| `docs/GPU/benchmark-results.md` | V1 benchmark methodology and numbers backing the table above |

---

## Upstream & Submodule

```bash
# Sync with upstream picoclaw
git fetch upstream
git merge upstream/main

# Update engines/llamacli submodule (assix's precompiled llama-cli)
git submodule update --remote engines/llamacli
git add engines/llamacli && git commit -m "chore: bump engines/llamacli submodule"
```

---

## License

picoclaw: MIT · assix/Arduino-UnoQ-Optimized-Llama-CLI (`engines/llamacli`): MIT
