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

Forked from upstream [picoclaw](https://github.com/sipeed/picoclaw) — repo: [Uno-QClaw](https://github.com/laurenvil/Uno-QClaw) · current development branch: **`QClaw-v2`** · inference via the persistent **`pkg/providers/llamaserver`** provider with the `yzma` engine (self-contained at `engines/yzma/lib/`) · default model: Qwen3.5-0.8B Q4_0

QClaw ships three execution paths sharing the same model, system prompt, and 15-skill tree:

- **Agentic** — agent loop + 23-rule pre-router + 8 tools. End-to-end compile/flash, camera capture, MPU LED control, network diagnostics, I²C bus scan.
- **Direct** — same 23-rule pre-router + single LLM call, no tools, no loop. Faster Q&A across all 15 skills.
- **TUI Chat** — full-screen launcher TUI with an embedded chat surface (Direct and Agentic modes, live streaming, server pre-warmed at launch).


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
| Answer hardware questions | All | Pre-router inlines the relevant skill content (15 skills covered) |
| Chat with streaming tokens | TUI | Direct and Agentic modes; server pre-warmed at launch; F2 switches mode |
| Channel configuration | TUI | Full-screen panel to configure Telegram, Discord, and other channels |
| Telegram, terminal, SSH | Agentic | qclaw channel adapters |
| Fully offline | All | All inference, compilation, and flashing runs locally on the QRB2210 |

---

## Quick Start

```bash
git clone --recursive https://github.com/laurenvil/Uno-QClaw.git ~/ArduinoApps/QClaw
cd ~/ArduinoApps/QClaw
git checkout QClaw-v2

# --recursive pulls the yzma submodule (engines/yzma/lib/ — llama-server + .so files, no build needed)

# Download the model (~490 MB for Q4_0)
mkdir -p ~/models
wget -O ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf \
  'https://huggingface.co/Qwen/Qwen3.5-0.8B-GGUF/resolve/main/Qwen3.5-0.8B-Q4_0.gguf'

# Build, install arduino-cli, configure (one time)
make qclaw-install

# Start a session
make qclaw-agentic    # agent loop + 8 tools — compile/upload/camera/sysfs_led/network/i2cdetect
make qclaw-direct     # pre-router + single LLM call, no tools — fast Q&A
make qclaw-tui        # full-screen TUI: channel config + in-app chat (server pre-warms at launch)

# Or invoke directly
qclaw direct --model yzma -m "Which pins do PWM?"
```

`make qclaw-install` builds the binary, installs the system prompt and 15-skill tree, downloads `arduino-cli`, installs the `arduino:zephyr` board core, and runs the interactive setup wizard. `make qclaw` is an alias for `make qclaw-agentic`.

<img width="4000" height="3000" alt="QClaw-TUI" src="https://github.com/user-attachments/assets/8f73e0da-bb7f-46d7-9415-9d667144ade2" />

---

## Three Execution Paths

All three paths share the same `yzma` engine, the same `SOUL.md`, and the same 23-rule pre-router. They differ in what surrounds the LLM call and how the server is started.

| Aspect | `make qclaw-agentic` | `make qclaw-direct` | `make qclaw-tui` |
|---|---|---|---|
| Agent loop (multi-iteration) | ✅ | ❌ (single call) | ✅ in Agentic mode |
| Tools available | **8** | None | **8** in Agentic mode |
| Pre-router | ✅ 23 rules | ✅ same 23 rules | ✅ same 23 rules |
| Token streaming | ✅ | ❌ | ✅ live in TUI |
| Compile / upload sketches | ✅ | ❌ text-only | ✅ Agentic mode |
| Camera / LED / network / I²C | ✅ | ❌ | ✅ Agentic mode |
| Telegram gateway | ✅ | ❌ | ❌ (Chat ⊕ Gateway) |
| Server start | On first message | On first message | **At TUI launch** |
| Best for | Multi-step hardware workflows | Fast factual Q&A | Interactive testing, config, Q&A |

Use the Direct path for fast factual Q&A and text-only sketch generation. Use the Agentic path (CLI or TUI Agentic mode) whenever you need to compile, flash, or call any hardware tool. The TUI is the best environment for iterative testing — the server is already warm when you open Chat.

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
- **Role:** Host environment running the `qclaw` agent framework (which manages the persistent `engines/yzma/lib/llama-server` inference process), local compilation toolchain, and debugging suites.

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
│  Agentic path (make qclaw-agentic)                                 │
│  ┌──────────────────────────────────────────────────────┐         │
│  │ qclaw agent / gateway (Go)                            │        │
│  │   ├── channels/  (Telegram, terminal, IRC, Matrix, …) │        │
│  │   ├── pre-router (skill_preload.go, 23 rules)         │        │
│  │   ├── agent loop (multi-iter, tool dispatch)          │        │
│  │   └── tools (8):                                      │        │
│  │       • arduino   → arduino-cli + OpenOCD@0x8100000   │        │
│  │       • camera / sysfs_led / network / i2cdetect      │        │
│  │       • read_file / write_file / list_dir             │        │
│  └──────────────────────────────────────────────────────┘         │
│                                                                    │
│  Direct path (make qclaw-direct)                                   │
│  ┌──────────────────────────────────────────────────────┐         │
│  │ qclaw direct  (native Go)                             │        │
│  │   └── pre-router (23 rules, 15 skills)                │        │
│  │   └── ProcessDirectSingleTurn() — single call, no tools│        │
│  └──────────────────────────────────────────────────────┘         │
│                                                                    │
│  TUI Chat (make qclaw-tui)                                         │
│  ┌──────────────────────────────────────────────────────┐         │
│  │ qclaw-launcher-tui (full-screen tview TUI)            │        │
│  │   ├── channel config, gateway management              │        │
│  │   └── Chat page (Direct / Agentic, streaming)         │        │
│  │       • server pre-warmed via WarmUp() at TUI launch  │        │
│  └──────────────────────────────────────────────────────┘         │
│                                                                    │
│                          OpenAI-compat HTTP + SSE                  │
│  pkg/providers/llamaserver ───►  127.0.0.1:8083/v1/chat/...        │
│     (persistent server, spawned once per process)   │              │
│                                                      ▼             │
│                              ┌────────────────────────────┐        │
│                              │ yzma ⭐  (CPU, ARMv8.0)    │        │
│                              │ engines/yzma/lib/          │        │
│                              └────────────────────────────┘        │
│                                                                    │
│  Submodule: engines/yzma/ → hybridgroup/yzma (self-contained lib/) │
└────────────────────────────────────────────────────────────────────┘
```

### Multi-Engine `llamaserver` Provider

QClaw-v2 uses a **persistent on-device HTTP server** (`pkg/providers/llamaserver`) instead of a subprocess per call. The provider spawns `engines/yzma/lib/llama-server` once, health-checks it on `127.0.0.1:8083`, and proxies all `Chat()` calls through the OpenAI-compatible `/v1/chat/completions` endpoint. Adding a new engine is a config-only change — no Go rebuild needed.

Config layout (`config/qclaw.config.json` and runtime `~/.qclaw/config.json`):

```jsonc
"model_list": [
  {
    "model_name":      "yzma",
    "model":           "llama-server/Qwen_Qwen3.5-0.8B-Q4_0.gguf",
    "api_base":        "engines/yzma/lib/llama-server",   // relative to repo root
    "api_key":         "local",
    "request_timeout": 1200,
    "extra_body": {
      "models_dir": "~/models",
      "threads":    4,
      "ctx_size":   8192,
      "parallel":   1,                                    // pin to 1 — keep full ctx per request
      "port":       8083,
      "lib_path":   "engines/yzma/lib",                   // → LD_LIBRARY_PATH prepend
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

### Engine

| Engine key | Binary | Build / size | Status |
|---|---|---|---|
| `yzma` ⭐ | `engines/yzma/lib/llama-server` | b9127 a9883db8e, dyn 9.0 MB | ✅ Default; CPU-only (ARMv8.0 dispatch) |

The engine is selected by `agents.defaults.model_name` in `~/.qclaw/config.json`, or overridden per-call with `--model yzma`. Additional engines can be added by dropping a `llama-server` binary and a `model_list` entry — no Go rebuild needed.

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

Everything runs locally on the QRB2210 over a 127.0.0.1 loopback — the `llamaserver` provider keeps one llama-server child process up between requests, so follow-up turns within the same session skip the cold model-load entirely.

---

## Benchmarks (Arduino Uno Q)

Model: `Qwen_Qwen3.5-0.8B-Q4_0.gguf` · `-c 8192 -t 4 -np 1 --reasoning off --jinja` · QClaw-v2 persistent llama-server.

### Engine Benchmarks — pwm_pins cold (Run 7)

| Engine | Wall (cold) | Response | Notes |
|---|---|---|---|
| `yzma` ⭐ baseline | **11m49.6s** | ✅ 241 chars | Fastest; CPU ARMv8.0 |
| `yzma` + study-bible flags | 12m43.2s | ✅ 146 chars | +53 s cold regression; better on warm steady-state |

The study-bible flags (`--flash-attn on --mlock --cache-type-k/v q8_0`) pay upfront costs (mlock pins at load, flash-attn has no ARMv8.0 fast-path) that aren't recouped in a single cold call. They are included in the default config because they pay off across a long-lived gateway session.

Full write-up: [`docs/benchmarks/run7/yzma-optimized-benchmark.md`](docs/benchmarks/run7/yzma-optimized-benchmark.md) · full history: [`docs/benchmarks/BENCHMARK_SUMMARY.md`](docs/benchmarks/BENCHMARK_SUMMARY.md)

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
| `make qclaw-tui` | **TUI launcher**: channel config + in-app Chat with server pre-warm |
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
├── cmd/
│   ├── qclaw/                    # CLI entry point (Cobra) — agentic gateway + direct subcommand
│   └── qclaw-launcher-tui/       # Full-screen TUI (make qclaw-tui)
│       └── internal/ui/
│           ├── app.go            #   appState, triggerPrewarm(), openChat()
│           └── chat.go           #   chatPage — Direct/Agentic modes, preWarm(), streaming
├── pkg/
│   ├── agent/                  # Agent loop, context, pre-router, tool dispatch
│   ├── channels/               # Telegram, terminal, IRC, Matrix, ...
│   ├── providers/
│   │   ├── llamaserver/        # ⭐ Persistent on-device llama-server provider (default)
│   │   ├── openai_compat/      #   HTTP client used by llamaserver and cloud providers
│   │   └── factory_provider.go #   model_list → provider-instance wiring
│   └── tools/                  # arduino, camera, sysfs_led, network, i2cdetect, filesystem
├── engines/yzma/             # Submodule → hybridgroup/yzma (b9127)
│   └── lib/                  #   ⭐ self-contained: llama-server + .so files (ARMv8.0, no build)
├── config/qclaw.config.json  # Runtime config template
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
│   └── bench-llamaserver-provider.sh # llama-server bench
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
| `docs/QClaw/development/setup-walkthrough.md` | Step-by-step from a fresh Uno Q to a running QClaw (all three paths) |
| `docs/QClaw/development/architecture-study-bible.md` | Dual-processor architecture, pin tables, voltage rules, three data paths |
| `docs/QClaw/development/tui-chat-design.md` | TUI Chat design: pre-warm lifecycle, Direct/Agentic modes, session keys |
| `docs/QClaw/development/launch-and-debug.md` | llamaserver provider debugging: pre-flight checks, failure modes, log reading |
| `docs/QClaw/whitepaper.md` | Architecture and evaluation whitepaper |
| `docs/QClaw/capability-integration.md` | Skill, reference, and tool integration record |
| `docs/QClaw/mcu-communication-whitepaper.md` | MPU↔MCU compile/flash pipeline deep dive |
| `docs/benchmarks/BENCHMARK_SUMMARY.md` | All benchmark runs with engine comparisons |

---

## Upstream & Submodules

```bash
# Sync with upstream picoclaw
git fetch upstream
git merge upstream/main

# Update yzma submodule (hybridgroup/yzma — engine for Uno Q)
git submodule update --remote engines/yzma
git add engines/yzma && git commit -m "chore: bump engines/yzma submodule"

# Refresh the yzma binaries/libs after a submodule bump
cd engines/yzma && make download-llama.cpp
#   or: make download-llama.cpp VERSION=b9127
```

---

## License

picoclaw: MIT · hybridgroup/yzma (`engines/yzma`): Apache-2.0
