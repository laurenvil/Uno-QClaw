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

Forked from upstream [picoclaw](https://github.com/sipeed/picoclaw) — repo: [Uno-QClaw](https://github.com/laurenvil/Uno-QClaw) · inference via [yzma](https://github.com/hybridgroup/yzma) · default model: Qwen3.5-0.8B Q4_0

QClaw ships two execution paths sharing the same model, system prompt, and 15-skill tree:

- **Agentic** — agent loop + 23-rule pre-router + 8 tools. End-to-end compile/flash, camera capture, MPU LED control, network diagnostics, I²C bus scan.
- **Direct** — same 23-rule pre-router + single LLM call, no tools, no loop. Faster Q&A across all 15 skills.



https://github.com/user-attachments/assets/05a0e896-7eb6-4bb8-b494-1abc26eec687



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
git submodule update --init --recursive

# Download the inference engine
cd yzma && make download-llama.cpp && cd ..

# Download the model (~490 MB for Q4_0)
mkdir -p ~/models
wget -O ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf \
  'https://huggingface.co/Qwen/Qwen3.5-0.8B-GGUF/resolve/main/Qwen3.5-0.8B-Q4_0.gguf'

# Build, install arduino-cli, configure (one time)
make qclaw-install

# Start a session — pick a path
make qclaw-agentic    # full agent loop + 8 tools (compile/upload/camera/sysfs_led/network/i2cdetect)
make qclaw-direct     # pre-router + direct API (fast Q&A, no tools)
```

`make qclaw-install` builds the binary, installs the system prompt and 15-skill tree, downloads `arduino-cli`, installs the `arduino:zephyr` board core, and runs the interactive setup wizard. `make qclaw` is an alias for `make qclaw-agentic`.

---

## Two Execution Paths

Both paths share the same llama-server backend, the same `SOUL.md`, and the same 23-rule pre-router. They differ only in what surrounds the LLM call.

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
- **Role:** Host environment running the `llama-server` inference engine, `qclaw` agent framework, local compilation toolchain, and debugging suites.

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
│  │ qclaw-direct-chat.py (terminal REPL)                │       │
│  │   ├── pre-router (same 23 rules, Python port)       │       │
│  │   └── single LLM call · no tools · no loop          │       │
│  └────────────────────────────────────────────────────┘       │
│                                                                │
│                       │ HTTP loopback :8080                    │
│  llama-server  ◄──────┘                                        │
│    └── yzma/  (submodule, llama.cpp FFI)                       │
└──────────────────────────────────────────────────────────────┘
```

The pre-router (`pkg/agent/skill_preload.go`, mirrored for the direct path in `scripts/qclaw-direct-chat.py`) scans the user message against 23 keyword regex rules spanning 15 skills. Each match inlines the corresponding `SKILL.md` and reference files into the system prompt before the LLM call — the model never has to call `read_file` for known skill content.

| Domain | Skills | Sample triggers |
|---|---|---|
| Sketch fundamentals | `sketch-patterns` | `breathe`, `blink`, `button`, `analogRead`, `servo`, `compile`, `upload`, `CAN bus`, `DAC`, `OPAMP` |
| LED matrix | `led-matrix` | `matrix`, `scroll`, `Arduino_LED_Matrix` |
| Hardware reference | `uno-q-hardware` | `pin`, `5V`, `voltage`, `JDIGITAL`, `Qwiic`, `USB-C`, `VIN` |
| Dual-chip workflow | `bridge`, `arduino-app-lab` | `Bridge`, `Python + sketch`, `App Lab`, `Brick` |
| Linux-side capabilities | `wireless`, `vision`, `audio`, `linux-led` | `Wi-Fi`, `Bluetooth`, `camera`, `OpenCV`, `microphone`, `red:user` |
| Plug-and-play sensors | `modulino` | `Modulino`, `ModulinoDistance` |

The `arduino` tool compiles via `arduino-cli`, then flashes via OpenOCD directly to the STM32U585 sketch partition at `0x8100000`. (The pre-installed `arduino-flash` wrapper hardcodes `0x80F0000`, which lands in a reserved area near the end of bank 1 and never executes — see `docs/QClaw/whitepaper.md` for the root-cause analysis.)

Everything runs locally over `127.0.0.1:8080`.

---

## Benchmarks (Arduino Uno Q)

Model: `Qwen_Qwen3.5-0.8B-Q4_0.gguf` · `--ctx-size 8192 --parallel 1 --reasoning-budget 800` · `/no_think` active · t=0.3. Walltimes are full end-to-end (cold prefill + decode) on a fresh server.

### Throughput & resource footprint

| Metric | Value |
|---|---|
| Decode throughput (0.8B Q4_0) | ~8 tok/s |
| Model RAM (0.8B Q4_0, mlocked) | ~490 MB |
| KV cache (8192 ctx, q8_0 K+V) | ~120 MB |
| Total llama-server RSS | ~1.3 GB |
| Boot-to-ready (cold model load) | ~6 s |
| Time to first token (warm KV) | ~1 s |
| Time to first token (cold prefill, 20K-char prompt) | ~25 s |

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
├── yzma/                     # Submodule → hybridgroup/yzma (llama.cpp FFI)
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
| `docs/QClaw/development/architecture-study-bible.md` | Dual-processor architecture, pin tables, voltage rules, data paths |
| `docs/QClaw/development/UnoQ-datasheet.pdf` | Official Arduino Uno Q hardware datasheet |
| `docs/QClaw/whitepaper.md` | Architecture and evaluation whitepaper |
| `docs/QClaw/capability-integration.md` | Skill, reference, and tool integration record |
| `docs/QClaw/mcu-communication-whitepaper.md` | MPU↔MCU compile/flash pipeline deep dive |

---

## Upstream & Submodule

```bash
# Sync with upstream picoclaw
git fetch upstream
git merge upstream/main

# Update yzma submodule
git submodule update --remote yzma
git add yzma && git commit -m "chore: update yzma submodule"
```

---

## License

picoclaw: MIT · yzma: Apache-2.0
