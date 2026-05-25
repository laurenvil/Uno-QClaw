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

Forked from upstream [picoclaw](https://github.com/sipeed/picoclaw) — repo: [Uno-QClaw](https://github.com/laurenvil/Uno-QClaw) · current development branch: **`QClaw-v2`** · inference via the new persistent **`pkg/providers/llamaserver`** provider with four interchangeable engines (`assix-mpu`, `surgical`, `assix-adreno`, `yzma`) selectable by config · default model: Qwen3.5-0.8B Q4_0

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
git clone --recursive https://github.com/laurenvil/Uno-QClaw.git ~/ArduinoApps/QClaw
cd ~/ArduinoApps/QClaw
git checkout QClaw-v2

# --recursive pulls both submodules:
#   engines/llamacli  (assix-bundled llama-server + llama.cpp source)
#   yzma              (hybridgroup/yzma — fastest engine, self-contained at yzma/lib/)

# Download the model (~490 MB for Q4_0)
mkdir -p ~/models
wget -O ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf \
  'https://huggingface.co/Qwen/Qwen3.5-0.8B-GGUF/resolve/main/Qwen3.5-0.8B-Q4_0.gguf'

# Build, install arduino-cli, configure (one time)
make qclaw-install

# Start a session
make qclaw-agentic    # agent loop + 8 tools — compile/upload/camera/sysfs_led/network/i2cdetect
make qclaw-direct     # pre-router + single LLM call, no tools — fast Q&A

# Or invoke a specific engine directly
qclaw direct --model yzma         -m "Which pins do PWM?"
qclaw direct --model assix-mpu    -m "Which pins do PWM?"
```

`make qclaw-install` builds the binary, installs the system prompt and 15-skill tree, downloads `arduino-cli`, installs the `arduino:zephyr` board core, and runs the interactive setup wizard. `make qclaw` is an alias for `make qclaw-agentic`.

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

The agent loop's response-format scaffolding contributes real quality on complex code generation, not just tool-call mechanics. Use the direct path for fast factual Q&A and sketch generation (text-only); use the agentic path whenever you need to compile, flash, or call any hardware tool.

The agent loop's response-format scaffolding contributes real quality on complex code generation, not just tool-call mechanics. The pre-router alone is necessary but not sufficient for harder prompts at 0.8B scale — use agentic mode for anything beyond simple Q&A.

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
┌────────────────────────────────────────────────────────────────────┐
│                       QClaw (this repo)                            │
│                                                                    │
│  Agentic path                                                      │
│  ┌──────────────────────────────────────────────────────┐         │
│  │ qclaw agent / gateway (Go)                            │        │
│  │   ├── channels/  (Telegram, terminal, IRC, Matrix, …) │        │
│  │   ├── pre-router (skill_preload.go, 23 rules)         │        │
│  │   ├── agent loop (multi-iter, tool dispatch)          │        │
│  │   └── tools (8):                                      │        │
│  │       • read_file / write_file / list_dir             │        │
│  │       • arduino   → arduino-cli + OpenOCD@0x8100000   │        │
│  │       • camera    → gst-launch-1.0 v4l2src ! ...      │        │
│  │       • sysfs_led → /sys/class/leds/*/brightness      │        │
│  │       • network   → /proc/net/route + interfaces      │        │
│  │       • i2cdetect → /dev/i2c-* + i2cdetect -y -r      │        │
│  └──────────────────────────────────────────────────────┘         │
│                                                                    │
│  Direct path                                                       │
│  ┌──────────────────────────────────────────────────────┐         │
│  │ qclaw direct  (native Go — cmd/qclaw/internal/        │        │
│  │               agent/direct.go)                        │        │
│  │   └── pre-router (23 rules, 15 skills)                │        │
│  │   └── ProcessDirectSingleTurn() (pkg/agent/loop.go)   │        │
│  │       single LLM call, no tools, no loop              │        │
│  └──────────────────────────────────────────────────────┘         │
│                                                                    │
│                          OpenAI-compat HTTP                        │
│  pkg/providers/llamaserver ───►  127.0.0.1:<port>/v1/chat/...      │
│     (persistent server,             │                              │
│      auto-spawned by factory)       ▼                              │
│                              one of four engines:                  │
│                              ┌────────────────────────────┐        │
│                              │ assix-mpu    (CPU only)    │        │
│                              │ surgical     (ggml-org)    │        │
│                              │ assix-adreno (Adreno OCL)  │        │
│                              │ yzma  ⭐     (CPU only)    │        │
│                              └────────────────────────────┘        │
│                                                                    │
│  Submodules:                                                       │
│    engines/llamacli/  → assix/Arduino-UnoQ-Optimized-Llama-CLI     │
│    yzma/              → hybridgroup/yzma (self-contained lib/)     │
└────────────────────────────────────────────────────────────────────┘
```

### Multi-Engine `llamaserver` Provider

QClaw-v2 swapped the per-`Chat()` subprocess (`pkg/providers/llamacli` driving `engines/llamacli/mpu/llama-cli`) for a **persistent on-device HTTP server** (`pkg/providers/llamaserver`). The same provider code can launch any compliant `llama-server` binary; engine selection is config-only.

Config layout (`config/qclaw.config.json` and runtime `~/.qclaw/config.json`):

```jsonc
"model_list": [
  {
    "model_name":    "yzma",
    "model":         "llama-server/Qwen_Qwen3.5-0.8B-Q4_0.gguf",
    "api_base":      "yzma/lib/llama-server",
    "request_timeout": 1200,
    "extra_body": {
      "models_dir": "~/models",
      "threads":    4,
      "ctx_size":   8192,
      "parallel":   1,
      "port":       8083,
      "lib_path":   "yzma/lib",
      "extra_args": [
        "--flash-attn", "on", "--mlock",
        "--cache-type-k", "q8_0", "--cache-type-v", "q8_0",
        "--reasoning-budget", "800"
      ]
    }
  }
]
```

| Provider option | `extra_body` key | What it does |
|---|---|---|
| `WithModelsDir` | `models_dir` | Where to resolve `model` paths |
| `WithThreads` | `threads` | `-t` — Cortex-A53 cores |
| `WithContextSize` | `ctx_size` | `-c` — KV cache budget |
| `WithParallel` | `parallel` | `-np` — KV slots; **pinned to 1** to keep full ctx per request (auto picks ≥2 on b9127+ and splits) |
| `WithPort` | `port` | Loopback listener port |
| `WithLibraryPath` | `lib_path` | Prepended to `LD_LIBRARY_PATH` for dynamically-linked builds |
| `WithExtraArgs` | `extra_args` | Verbatim flags appended to the server command — per-engine tuning escape hatch |
| `WithTimeout` | (from `request_timeout`) | Cold-prefill budget on the HTTP client |

The provider always pins these flags itself:

```
-m <modelPath>  --host 127.0.0.1  --port <port>
-t <threads>    -c <ctxSize>      -np <parallel>
--reasoning off  --jinja  --log-disable
```

Then any `extra_args` from config are appended.

### Engine Catalog

| Engine key | Binary | Build / size | Status |
|---|---|---|---|
| `assix-mpu` | `engines/llamacli/mpu/llama-server` | aca9a0f, static 16 MB | ✅ Reliable; OpenCL drops at init, CPU fallback |
| `surgical` | `llama.cpp/build/bin/llama-server` | ggml-org 832d383, dyn 9.8 MB | ❌ `GGML_ASSERT(0)` mid-decode on FD702 |
| `assix-adreno` | `engines/llamacli/llama.cpp/build-adreno/bin/llama-server` | aca9a0f fresh, dyn 9.8 MB | ❌ rusticl `sub_group_reduce_add` undeclared |
| `yzma` ⭐ | `yzma/lib/llama-server` | b9127 a9883db8e, dyn 9.0 MB | ✅ Fastest; CPU-only (RPC + armv8 dispatch) |

Switch engines without rebuilding by setting `agents.defaults.model_name` (or passing `--model <name>` to `qclaw direct`).

### Study-Bible Optimization Flags (via `extra_args`)

The architecture study bible documents five tunables for ARM CPU inference:

| Flag | Effect | Notes |
|---|---|---|
| `--flash-attn on` | Fused QK·softmax·V kernel — ~10% theoretical | No ARMv8.0 fast-path; modest in practice |
| `--mlock` | Pins model weights in RAM (no swap) | Pays full pinning cost up front on cold runs |
| `--cache-type-k q8_0` / `-v q8_0` | Quantize KV cache to int8 — halves KV RAM | Mild per-token quant overhead |
| `--reasoning-budget 800` | Cap `<think>` tokens | Belt-and-braces with `/no_think` in SOUL.md |

These are not a free win. Run 7 measured a **53 s cold regression** on yzma (12m43s vs 11m49.6s baseline) — mlock and flash-attn pay upfront costs that aren't recouped in a single cold call. They are better candidates for a long-lived persistent server in warm steady-state. See [`docs/benchmarks/run7/yzma-optimized-benchmark.md`](docs/benchmarks/run7/yzma-optimized-benchmark.md).

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

Everything runs locally on the QRB2210 over a 127.0.0.1 loopback — the `llamaserver` provider keeps one llama-server child process up between requests, eliminating the cold-mmap cost that the older subprocess-per-`Chat()` `llamacli` path paid on every turn.

---

## Benchmarks (Arduino Uno Q)

Model: `Qwen_Qwen3.5-0.8B-Q4_0.gguf` · `-c 8192 -t 4 -np 1 --reasoning off --jinja` · QClaw-v2 persistent llama-server.

### Engine Comparison — pwm_pins cold (Run 6 + Run 7)

| Engine | Wall (cold) | Response | Backend |
|---|---|---|---|
| `yzma` ⭐ (baseline) | **11m49.6s** | ✅ 241 chars | RPC + CPU armv8 |
| `yzma` (study-bible flags) | 12m43.2s | ✅ 146 chars | RPC + CPU armv8 |
| `assix-mpu` | 17m54s | ✅ 427 chars | OpenCL→CPU fallback |
| `surgical` | crash @ 57s | ❌ | OpenCL `GGML_ASSERT(0)` mid-decode |
| `assix-adreno` | hung (killed) | ❌ | OpenCL `sub_group_reduce_add` undeclared on rusticl |

**Yzma is the fastest engine tested**, beating `assix-mpu` by **6m04s** (~34%) on the same prompt, model, and 4× Cortex-A53. The study-bible flags (`--flash-attn on --mlock --cache-type-k/v q8_0`) added a 53 s cold regression — they pay upfront costs better amortised on a warm persistent server.

Full per-run write-ups: [`docs/benchmarks/run6/three-engine-comparison.md`](docs/benchmarks/run6/three-engine-comparison.md), [`docs/benchmarks/run7/yzma-optimized-benchmark.md`](docs/benchmarks/run7/yzma-optimized-benchmark.md), and [`docs/benchmarks/BENCHMARK_SUMMARY.md`](docs/benchmarks/BENCHMARK_SUMMARY.md) for the full 7-run history including the older llama-cli reference numbers (10.6 t/s PP / 8.8 t/s TG warm).

### Per-prompt walltime — Agentic vs Direct (legacy llama-cli reference)

Numbers below are from the older subprocess-per-`Chat()` `pkg/providers/llamacli` track (`engines/llamacli/mpu/llama-cli`, b9099). They are kept here as a quality reference — the QClaw-v2 `llamaserver` track is on a different cost curve (one cold server load, then near-instant follow-ups within the same session).

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
Uno-QClaw/  (branch: QClaw-v2)
├── cmd/qclaw/             # CLI entry point (Cobra)
├── pkg/
│   ├── agent/                  # Agent loop, context, pre-router, tool dispatch
│   ├── channels/               # Telegram, terminal, IRC, Matrix, ...
│   ├── providers/
│   │   ├── llamaserver/        # ⭐ Persistent on-device llama-server provider (default)
│   │   ├── llamacli/           #   Legacy subprocess-per-Chat driver (kept for the v3 track)
│   │   ├── openai_compat/      #   HTTP client used by llamaserver and cloud providers
│   │   └── factory_provider.go #   model_list → provider-instance wiring
│   └── tools/                  # arduino, camera, sysfs_led, network, i2cdetect, filesystem
├── engines/llamacli/         # Submodule → assix/Arduino-UnoQ-Optimized-Llama-CLI
│   ├── mpu/llama-server      #   precompiled aarch64 ELF (assix, 16 MB static)
│   ├── mpu/llama-cli         #   precompiled CLI ELF (legacy track)
│   └── llama.cpp/            #   source tree (build-adreno/ is the rebuilt Adreno engine)
├── yzma/                     # Submodule → hybridgroup/yzma (b9127)
│   └── lib/                  #   ⭐ self-contained: llama-server + 25 .so files
├── llama.cpp/                # Source tree for the `surgical` engine build (build/bin/llama-server)
├── config/qclaw.config.json  # Runtime config template (4-engine model_list)
├── workspace/
│   ├── SOUL.md               # System prompt / agent persona (must start with /no_think)
│   ├── IDENTITY.md           # Identity file
│   └── skills/               # Pre-router-loaded skill bundles (15 skills)
├── scripts/
│   ├── qclaw-launch.sh        # Agentic launcher
│   ├── qclaw-launch-direct.sh # Direct launcher
│   ├── qclaw-direct-chat.py   # Direct-path Python REPL
│   ├── qclaw-onboard.sh       # Setup wizard
│   ├── arduino-cli-setup.sh   # arduino-cli + arduino:zephyr installer
│   ├── bench-llamacli-provider.sh    # Legacy llama-cli bench
│   └── bench-llamaserver-provider.sh # llama-server CPU vs GPU bench
├── assets/qclaw-logo.svg
├── docs/
│   ├── QClaw/                # Technical references (see below)
│   └── benchmarks/           # Runs 1–7, BENCHMARK_SUMMARY.md
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

## Upstream & Submodules

```bash
# Sync with upstream picoclaw
git fetch upstream
git merge upstream/main

# Update engines/llamacli submodule (assix's precompiled llama-server + llama-cli)
git submodule update --remote engines/llamacli
git add engines/llamacli && git commit -m "chore: bump engines/llamacli submodule"

# Update yzma submodule (hybridgroup/yzma main — fastest engine on Uno Q)
git submodule update --remote yzma
git add yzma && git commit -m "chore: bump yzma submodule"

# Refresh the yzma binaries/libs (after a submodule bump)
cd yzma && make download-llama.cpp
#   or: make download-llama.cpp VERSION=b9127
```

---

## License

picoclaw: MIT · assix/Arduino-UnoQ-Optimized-Llama-CLI (`engines/llamacli`): MIT
