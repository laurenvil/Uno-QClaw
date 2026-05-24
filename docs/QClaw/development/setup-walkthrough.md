# QClaw Setup Walkthrough

Step-by-step guide to run QClaw on an Arduino Uno Q — from a fresh board to a working AI assistant that writes, compiles, and uploads Arduino sketches.

v3 ships **two execution paths**, both backed by the in-tree `pkg/providers/llamacli` which spawns the precompiled `engines/llamacli/mpu/llama-cli` (assix) as a subprocess per `Chat()`:

- **Agentic** (`make qclaw-agentic` / `make qclaw`) — full agent loop + 8 tools (read/write/list/arduino/camera/sysfs_led/network/i2cdetect); can compile and flash sketches end-to-end.
- **Direct** (`make qclaw-direct` / `qclaw direct`) — native Go implementation (`ProcessDirectSingleTurn` in `pkg/agent/loop.go`). Same 23-rule pre-router + 15-skill tree, single LLM call, no tools, no loop. Fast Q&A across all 15 skills; cannot compile or flash sketches.

See `docs/QClaw/whitepaper.md` and `docs/GPU/llama-cli-provider-whitepaper.md` for the design rationale.

---

## Prerequisites

| Item | Details |
|---|---|
| Board | Arduino Uno Q (QRB2210, 4 GB RAM, Debian Linux) |
| Go 1.25.7+ | For building the QClaw binary (v3 toolchain requirement) |
| Python 3.10+ | For the direct-path REPL (uses stdlib only — no pip install) |
| Git | To clone the repo |
| curl or wget | For downloading the model and arduino-cli |
| OpenOCD | Pre-installed at `/opt/openocd/` on stock Uno Q images — used by the agentic path to flash sketches |
| Telegram bot token | Optional — from @BotFather on Telegram (agentic path only) |

---

## Step 1: Clone and Initialize

```bash
git clone https://github.com/laurenvil/Uno-QClaw.git ~/ArduinoApps/QClaw
cd ~/ArduinoApps/QClaw
git checkout qclaw
git submodule update --init --recursive
```

---

## Step 2: Verify the Inference Engine Submodule

The precompiled `llama-cli` ships **inside the repo** as a git submodule
(`engines/llamacli`, pulling assix's
[`Arduino-UnoQ-Optimized-Llama-CLI`](https://github.com/assix/Arduino-UnoQ-Optimized-Llama-CLI)
snapshot). After Step 1's `git submodule update --init --recursive`, the
binary is already on disk at `engines/llamacli/mpu/llama-cli`.

```bash
ls -la engines/llamacli/mpu/llama-cli
# ⇒ -rwxr-xr-x ... 12M ... engines/llamacli/mpu/llama-cli

./engines/llamacli/mpu/llama-cli --version 2>&1 | head -2
# ⇒ version: 9099 (5d5d2e15d)
# ⇒ built with GNU 13.3.0 for Linux aarch64
```

If the binary is missing (clone without `--recursive`, or shallow checkout),
fetch it explicitly:

```bash
git submodule update --init --recursive engines/llamacli
```

There is no `make download-llama.cpp` step any more — there is no
`llama-server` to start, no shared libraries to link, no FFI handshake.
The Go provider in `pkg/providers/llamacli` `fork+exec`s this single ELF
file per inference call.

---

## Step 3: Download the AI Model

v3 uses the **Q4_0** quantization as the primary model (~490 MB, faster prefill than Q6_K, equivalent quality on QClaw prompts per v3 eval).

```bash
mkdir -p ~/models
wget -O ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf \
  'https://huggingface.co/Qwen/Qwen3.5-0.8B-GGUF/resolve/main/Qwen3.5-0.8B-Q4_0.gguf'
```

Download once — it does not change.

---

## Step 4: Install Everything

```bash
make qclaw-install
```

This single command:
1. Builds the QClaw binary (`build/qclaw`)
2. Installs the system prompt (`SOUL.md`), identity files, and the **15-skill tree** (`sketch-patterns/`, `led-matrix/`, `uno-q-hardware/`, `bridge/`, `wireless/`, `vision/`, `audio/`, `arduino-app-lab/`, `modulino/`, `linux-led/`, plus general skills) to `~/.qclaw/workspace/`
3. Copies `config/qclaw.config.json` to `~/.qclaw/config.json` (first run only). The v3 config exposes **8 narrow tools**: `read_file`, `write_file`, `list_dir`, `arduino` (compile/flash), `camera` (V4L2 still capture), `sysfs_led` (MPU-side RGB LEDs), `network` (read-only IP/gateway/interfaces), `i2cdetect` (Linux I²C bus scan). General `exec`, `message`, `edit_file`, generic `i2c`/`spi` remain disabled — every new tool is narrowly scoped and validates inputs against allow-lists. Total schema overhead: ~3,400 chars.
4. Downloads and installs `arduino-cli` to `~/.local/bin/` if not present
5. Installs the `arduino:zephyr` board core for the Uno Q
6. Runs the interactive setup wizard:
   - Confirms model and inference engine are present
   - Confirms `arduino-cli` and board core status
   - Asks for an optional Telegram bot token (agentic path only)
   - Asks who can message the bot (leave blank for anyone on your network)

To re-run just the arduino-cli step later:

```bash
make qclaw-arduino-setup
```

To re-run just the onboarding wizard (to change the Telegram token, for example):

```bash
make qclaw-onboard
```

To reinstall the system prompt and skills tree after a `git pull`:

```bash
make qclaw-setup
```

---

## Step 5: Launch

`make qclaw-agentic` brings up the Telegram gateway (if configured) and the
agent terminal. There is no long-lived inference server to wait on — the
first `Chat()` call spawns `engines/llamacli/mpu/llama-cli` as a subprocess
(cold-load ~12 s for the 0.8B Q4_0 model), waits for its GBNF-constrained
stdout envelope, and reaps the child. The next call repeats the spawn but
benefits from the GGUF being in the page cache (warm-load ~3 s overhead
before the first prefill token).

### Path A — Agentic (default, supported)

```bash
make qclaw-agentic    # or simply: make qclaw
```

Starts the Telegram gateway (if configured) and the agent terminal. The agent loop drives multi-step workflows across **8 tools**:

| Tool | What users can ask QClaw to do |
|---|---|
| `arduino` | "Compile and upload this blink sketch" — flashes STM32U585 at `0x8100000` via OpenOCD |
| `camera` | "Take a picture and save it to /tmp" — V4L2 single-frame capture via GStreamer |
| `sysfs_led` | "Make the red Linux LED blink" — drives `/sys/class/leds/*/brightness` |
| `network` | "What's my board's IP for SSH?" — reads `/proc/net/route`, lists interfaces |
| `i2cdetect` | "Which I²C devices are on bus 0?" — scans `/dev/i2c-*` (read-only) |
| `read_file`, `write_file`, `list_dir` | Workspace navigation for multi-file projects |

The arduino tool invokes `arduino-cli compile --fqbn arduino:zephyr:unoq` then flashes the resulting `.elf-zsk.bin` via OpenOCD at sketch partition address `0x8100000`.

```
  ┌───────────────────────────────────────────┐
  │  🧘  Q  C  L  A  W                        │
  │      Arduino AI Assistant                  │
  │                                            │
  │  Type your question at 'You:' and press    │
  │  Enter. QClaw responds in a few seconds.   │
  │  Type 'exit' or Ctrl+C to quit.            │
  └───────────────────────────────────────────┘

You: Use the arduino tool to upload a blink sketch for D9 to the board.

QClaw: [calls arduino tool → compiles → flashes → confirms]
```

### Path B — Direct (`make qclaw-direct`)

```bash
make qclaw-direct
```

Starts a single-turn terminal session. The direct path is a native Go feature — `ProcessDirectSingleTurn` in `pkg/agent/loop.go`, invoked via the `direct` subcommand (`cmd/qclaw/internal/agent/direct.go`). It applies the same 23-rule pre-router and 15-skill tree as the agentic path, makes a single LLM call, prints the response, and exits. No tools, no agent loop, no Telegram gateway — terminal only.

Use it for fast factual Q&A, pinout lookups, and sketch generation where you intend to copy the code into the Arduino IDE manually. For anything requiring compile or flash, use Path A.

Press `Ctrl+C` to stop cleanly (either path).

---

## Step 6: Verify Sketch Compilation (Agentic Path Only)

In the agentic terminal, ask QClaw to compile a test sketch:

```
You: Use the arduino tool to compile a blink sketch for D9.
```

QClaw will call the `arduino` tool with `action=compile` internally. If compilation succeeds, it reports success. If there is an error, it reads the output, explains the problem in plain English, and fixes it.

To upload to the connected board:

```
You: Use the arduino tool to upload a blink sketch for D9.
```

**Naming the tool explicitly matters at 0.8B scale.** v3 evaluation found that ambient prompts ("write a blink sketch and upload it") sometimes produce a correct sketch in markdown without firing the tool. Directive prompts ("Use the arduino tool to upload...") trigger the tool reliably. See `docs/QClaw/whitepaper.md` for the full analysis.

To check which boards are connected:

```
You: What boards are connected?
```

To verify the flash actually worked, watch the board's LED matrix or measure the GPIO with a multimeter — the agent's "success" message means the bytes are at the correct flash partition, not that the sketch ran (those are normally the same thing on the Uno Q, but the distinction matters if you suspect a bad sketch).

---

## Quick Reference: Make Targets

| Command | What it does |
|---|---|
| `make qclaw` | Default — alias for `qclaw-agentic` |
| `make qclaw-agentic` | **Agentic path**: agent loop + 23-rule pre-router + 8 tools (compile/upload + camera + sysfs_led + network + i2cdetect + filesystem) |
| `make qclaw-direct` | **Direct path**: pre-router + single LLM call, no tools — fast Q&A (terminal only) |
| `make qclaw-install` | Full first-time setup (build + workspace + arduino-cli + wizard) |
| `make qclaw-onboard` | Re-run setup wizard (change Telegram token, allow list) |
| `make qclaw-setup` | Reinstall system prompt and skills tree after a git pull |
| `make qclaw-arduino-setup` | Install or update arduino-cli and the Uno Q board core |
| `make qclaw-stop` | Stop the QClaw gateway/agent (no llama-server to kill on this track) |
| `make qclaw-tui` | Launch the graphical channel configuration panel |

---

## Auto-start on Boot (Optional)

There is **no inference daemon to enable** — inference is in-process: each `Chat()` is a one-shot subprocess of `engines/llamacli/mpu/llama-cli`. What you can autostart is the QClaw *gateway* (which receives Telegram/IRC/Matrix/etc. messages and feeds the agent loop):

```ini
# /etc/systemd/system/qclaw-gateway.service
[Unit]
Description=QClaw gateway + agent loop
After=network-online.target

[Service]
WorkingDirectory=/home/arduino/ArduinoApps/QClaw
ExecStart=/home/arduino/ArduinoApps/QClaw/build/qclaw gateway
Environment=QCLAW_MODEL=/home/arduino/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf
Environment=LLAMA_CLI=/home/arduino/ArduinoApps/QClaw/engines/llamacli/mpu/llama-cli
Restart=on-failure
User=arduino

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now qclaw-gateway
```

The first inbound message pays the ~12 s cold-load cost as the kernel
mmap's the GGUF; subsequent messages within the same boot are
warm-cache (~3 s overhead before the first prefill token). To **warm the
page cache at boot** without spinning up the agent, drop a short oneshot
service that runs `cat ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf > /dev/null`
before `qclaw-gateway` starts.

---

## Troubleshooting

**"Asking QClaw..." appears on Telegram but no response arrives**

1. Confirm the binary is executable: `ls -la engines/llamacli/mpu/llama-cli` — must be `-rwxr-xr-x`. If the submodule was checked out with the wrong perms, `chmod +x` it.
2. Confirm the model is present: `ls -la ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf`.
3. Manually invoke the binary to surface its stderr: `./engines/llamacli/mpu/llama-cli -m ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf -p "hi" -n 8 -st 2>&1 | head -40` — this should produce ~8 tokens of output. If it segfaults, prints `Unsupported GPU`, or hangs, the GGUF or binary is the problem (not the agent loop).
4. Run the agent with debug logging: `./build/qclaw gateway --debug` — every `Chat()` logs the full subprocess argv plus exit code and stderr tail.
5. Confirm `request_timeout` in `~/.qclaw/config.json` is `1200` — the default 30 s times out during cold model load. Cold spawns take ~12 s; warm spawns ~3 s + decode.
6. End-to-end smoke test: `bash scripts/bench-llamacli-provider.sh` (Phase A.2 should print `[ Prompt: 10.6 t/s | Generation: 8.8 t/s ]` in ~10 s — if it doesn't, the regression is in the provider, not your agent setup).

**Responses are very slow (> 60 seconds)**

- Confirm `/no_think` is the first line of `~/.qclaw/workspace/SOUL.md` — without it, Qwen3 generates reasoning tokens before every response, adding 30–120 s
- Check RAM: `free -h` — each `llama-cli` subprocess peaks at ~1.1 GB RSS. If two `Chat()`s overlap and the board is also serving Telegram, you can swap (Uno Q has 1.8 GiB swap by default but I/O on swapped weights is brutally slow).
- Check that page cache has the model: `vmtouch ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf` (install with `apt install vmtouch`) — if 0 % is resident, the next call will pay the full mmap cost (~10 s on eMMC).

**Sketch compilation fails**

- Confirm `arduino-cli` is installed: `arduino-cli version`
- Confirm the board core is installed: `arduino-cli core list`
- If missing, run: `make qclaw-arduino-setup`
- Check arduino-cli is in PATH: run `source ~/.bashrc` then try again

**"model not found" error on startup**

Run `make qclaw-setup` — reinstalls the config template with the `qwen-local` model entry.

---

## Updating QClaw

```bash
git pull origin qclaw
make qclaw-setup   # reinstall SOUL.md and IDENTITY.md
make build          # rebuild the binary
make qclaw         # restart
```

---

## Verifying Performance

Target numbers for `Qwen_Qwen3.5-0.8B-Q4_0` on the `qclaw-llamaCLI` track
(`engines/llamacli/mpu/llama-cli`, `-c 2048 -t 4 --temp 0.0 --reasoning off`,
warm cache, `/no_think` active in `SOUL.md`):

| Metric | Target |
|---|---|
| Prompt processing (warm) | ~10.6 tok/s |
| Generation throughput (warm, n=64) | ~8.8 tok/s |
| End-to-end `Chat()` walltime (warm, 64-tok decode) | ~10 s |
| End-to-end `Chat()` walltime (cold mmap + grammar + 1 tok) | ~12 s |
| Per-`Chat()` `llama-cli` RSS peak | ~1.1 GB |
| Swap usage during single `Chat()` | 0 |

To reproduce these numbers end-to-end:

```bash
bash scripts/bench-llamacli-provider.sh
```

The script measures direct-binary t/s (Phase A), cold-start cost (Phase B),
and the full Go-provider `Chat()` walltime including subprocess spawn,
stdout capture, and envelope parse (Phase C). Full V1 benchmark
methodology and raw logs: [`docs/GPU/benchmark-results.md`](../../GPU/benchmark-results.md).
