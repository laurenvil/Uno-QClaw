# QClaw Setup Walkthrough

Step-by-step guide to run QClaw on an Arduino Uno Q — from a fresh board to a working AI assistant that writes, compiles, and uploads Arduino sketches.

**Current branch: `QClaw-v2`** — uses the **persistent `pkg/providers/llamaserver`** provider. One llama-server child process stays up across requests; the engine binary and flags are config-only (no rebuild). The default engine is `yzma` — self-contained at `engines/yzma/lib/`, no build required:

| Engine | Binary | Status |
|---|---|---|
| `yzma` ⭐ | `engines/yzma/lib/llama-server` (b9127, 9.0 MB) | Default; CPU-only, ARMv8.0 — works on fresh clone |

Two execution paths share the same model, system prompt, and 15-skill tree:

- **Agentic** (`make qclaw-agentic` / `make qclaw`) — full agent loop + 8 tools (read/write/list/arduino/camera/sysfs_led/network/i2cdetect); can compile and flash sketches end-to-end.
- **Direct** (`make qclaw-direct` / `qclaw direct`) — native Go implementation (`ProcessDirectSingleTurn` in `pkg/agent/loop.go`). Same 23-rule pre-router + 15-skill tree, single LLM call, no tools, no loop. Fast Q&A across all 15 skills.

See `docs/QClaw/v2/multi-engine-llamaserver-plan.md` for the multi-engine design rationale and `docs/QClaw/whitepaper.md` for the higher-level architecture context.

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
git clone --recursive https://github.com/laurenvil/Uno-QClaw.git ~/ArduinoApps/QClaw
cd ~/ArduinoApps/QClaw
git checkout QClaw-v2
git submodule update --init --recursive
```

`--recursive` pulls the `engines/yzma` submodule (`hybridgroup/yzma` — ships `lib/llama-server` + `.so` libs, no build needed).

---

## Step 2: Verify the Inference Engine

After Step 1, the yzma binary is at `engines/yzma/lib/llama-server`. It is dynamically linked against the `.so` files in the same directory — QClaw sets `LD_LIBRARY_PATH` automatically, but you can smoke-test it directly:

```bash
ls -la engines/yzma/lib/llama-server
LD_LIBRARY_PATH=engines/yzma/lib engines/yzma/lib/llama-server --version 2>&1 | head -3
# ⇒ load_backend: loaded CPU backend from .../libggml-cpu-armv8.0_1.so
# ⇒ version: 9127 (a9883db8e)
# ⇒ built with GNU 14.2.0 for Linux aarch64
```

If `engines/yzma/lib/llama-server` is missing (e.g., the submodule was bumped to a new tag), refresh the libs:

```bash
cd engines/yzma
make download-llama.cpp                  # latest llama.cpp release
make download-llama.cpp VERSION=b9127    # pin a specific build
cd ../..
```

The QClaw runtime resolves `api_base` and `lib_path` **relative to the repo root** (CWD when you run `qclaw`), so both engines work out of the box from a fresh clone — no environment variables, no symlinks.

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
3. Copies `config/qclaw.config.json` to `~/.qclaw/config.json` (first run only). The QClaw-v2 config exposes a **`model_list`** with the `yzma` engine (see Step 4a below) and **8 narrow tools**: `read_file`, `write_file`, `list_dir`, `arduino` (compile/flash), `camera` (V4L2 still capture), `sysfs_led` (MPU-side RGB LEDs), `network` (read-only IP/gateway/interfaces), `i2cdetect` (Linux I²C bus scan). General `exec`, `message`, `edit_file`, generic `i2c`/`spi` remain disabled — every new tool is narrowly scoped and validates inputs against allow-lists. Total schema overhead: ~3,400 chars.
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

## Step 4a: Engine Selection & Server Flags

QClaw-v2's `pkg/providers/llamaserver` provider spawns one llama-server child process per engine entry and keeps it alive between requests. The default engine is whatever `agents.defaults.model_name` points at in `~/.qclaw/config.json`. To switch engines for a single call, pass `--model <engine_name>`:

```bash
qclaw direct --model yzma -m "Which pins do PWM?"
```

### Anatomy of a `model_list` entry

Each engine is one object in `model_list[]`. The yzma entry is the canonical example:

```jsonc
{
  "model_name":       "yzma",
  "model":            "llama-server/Qwen_Qwen3.5-0.8B-Q4_0.gguf",
  "api_base":         "yzma/lib/llama-server",        // path to the binary (relative resolves from repo root)
  "api_key":          "local",
  "request_timeout":  1200,                            // seconds — cold-prefill budget
  "extra_body": {
    "models_dir":  "~/models",                         // → WithModelsDir   (model lookup root)
    "threads":     4,                                  // → WithThreads     (-t)
    "ctx_size":    8192,                               // → WithContextSize (-c)
    "parallel":    1,                                  // → WithParallel    (-np) — pin to 1!
    "port":        8083,                               // → WithPort        loopback
    "lib_path":    "yzma/lib",                         // → WithLibraryPath (LD_LIBRARY_PATH prepend)
    "extra_args": [                                    // → WithExtraArgs   (verbatim flags)
      "--flash-attn", "on",
      "--mlock",
      "--cache-type-k", "q8_0",
      "--cache-type-v", "q8_0",
      "--reasoning-budget", "800"
    ]
  }
}
```

### Server flags the provider always pins

These are not configurable — `pkg/providers/llamaserver/provider.go` injects them on every spawn:

```
-m <modelPath>  --host 127.0.0.1  --port <port>
-t <threads>    -c <ctxSize>      -np <parallel>
--reasoning off  --jinja  --log-disable
```

Then any `extra_args` from config are appended verbatim. The full spawn command for `qclaw direct --model yzma` with the recommended `extra_args`:

```
yzma/lib/llama-server \
  -m ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf \
  --host 127.0.0.1 --port 8083 \
  -t 4 -c 8192 -np 1 \
  --reasoning off --jinja --log-disable \
  --flash-attn on --mlock \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --reasoning-budget 800
```

### Why `parallel: 1` matters

llama-server's `--parallel` defaults to `-1 = auto`, which on build b9127+ allocates **≥2 KV slots** and divides `ctx_size` across them. With `ctx_size=8192` and auto-slot ≥4, each request only sees ~2048 tokens of context — not enough for the QClaw system prompt (SOUL.md + IDENTITY.md + pre-router skills ≈ 1500 tokens) plus a meaningful generation budget. Pinning `parallel: 1` keeps the full ctx for the single in-flight request. This is also the provider's default (`WithParallel(1)`) so older configs without an explicit `parallel` key still work.

### Study-bible `extra_args` flags (with caveat)

Five flags from `docs/QClaw/development/architecture-study-bible.md` are wired up by default in the yzma entry:

| Flag | Theoretical effect |
|---|---|
| `--flash-attn on` | ~10% speedup via fused QK·softmax·V kernel; lower KV memory pressure |
| `--mlock` | Pin model weights in RAM (no swap, no eviction under memory pressure) |
| `--cache-type-k q8_0` / `-v q8_0` | Quantize KV cache to int8 — ~halves KV RAM vs fp16 |
| `--reasoning-budget 800` | Cap `<think>` tokens (belt-and-braces with `/no_think` in SOUL.md) |

**Caveat:** Run 7 measured these flags as a **53 s cold regression** on yzma (12m43.2s vs 11m49.6s baseline). `--mlock` pays the full model-pin cost up front rather than mmap-on-access, and `--flash-attn on` lacks an ARMv8.0 fast-path that beats the scalar code. They are better candidates for a warm steady-state on a long-lived gateway. To disable them, remove the `extra_args` array from the yzma entry. See [`docs/benchmarks/run7/yzma-optimized-benchmark.md`](../../benchmarks/run7/yzma-optimized-benchmark.md).

### Adding a new engine

No Go changes needed for a new llama-server build — add a `model_list` entry with the binary path, port, and any required `lib_path`/`extra_args`, then commit the config update. Switching engines is a one-line change to `agents.defaults.model_name`. See `docs/QClaw/v2/multi-engine-llamaserver-plan.md` for the original plan and `pkg/providers/factory_provider.go` for the `llama-server`/`llamaserver` factory case.

---

## Step 5: Launch

Three execution paths share the same model, system prompt, and 15-skill tree. The llama-server child process (cold-load: ~3–5 min for the 0.8B Q4_0) is spawned **once** per process lifetime and kept up across all subsequent requests. The Path C TUI pre-warms the server at launch rather than waiting for the first message.

Sessions persist across QClaw restarts via `~/.qclaw/workspace/sessions/`. To force a clean cold start for a controlled benchmark:

```bash
pkill -f llama-server                              # kill any persistent server
rm -f ~/.qclaw/workspace/sessions/*                # drop session history
```

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

### Path C — TUI Chat (`make qclaw-tui`)

```bash
make qclaw-tui
```

Launches the full-screen TUI (`cmd/qclaw-launcher-tui`). Unlike Path A/B, the llama-server is **pre-warmed at TUI startup** — `appState.triggerPrewarm()` runs `llamaserver.Provider.WarmUp()` in a background goroutine as soon as the main menu appears. By the time you navigate to Chat, the cold-start cost has typically been paid.

The Chat page inside the TUI supports two modes switchable with F2:

| Mode | API | Notes |
|---|---|---|
| **Direct** | `ProcessDirectSingleTurnStream` | Pre-router + single LLM call; token-by-token streaming |
| **Agentic** | `ProcessAgenticWithProgressStream` | Full agent loop, tools, streaming; tool events shown inline |

After closing Chat (Esc), the old server is shut down cleanly and a new pre-warmed page is created for the next open. The TUI also manages channel configuration and can launch the gateway (`Start Gateway`). Chat and Gateway are mutually exclusive — one disables the other in the menu.

Keybindings inside Chat: `F2` toggle mode, `Ctrl+L` clear output, `Esc` return to menu.

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
| `make qclaw-tui` | **TUI launcher**: channel config + in-app Chat (Direct & Agentic modes, pre-warmed server) |

---

## Auto-start on Boot (Optional)

On QClaw-v2 the gateway owns the persistent llama-server process — when systemd starts `qclaw gateway`, the configured engine is spawned on first inbound message and stays up until the gateway exits. There is no separate inference daemon to enable.

```ini
# /etc/systemd/system/qclaw-gateway.service
[Unit]
Description=QClaw gateway + agent loop (manages persistent llama-server)
After=network-online.target

[Service]
WorkingDirectory=/home/arduino/ArduinoApps/QClaw
ExecStart=/home/arduino/ArduinoApps/QClaw/build/qclaw gateway
ExecStopPost=/usr/bin/pkill -f llama-server
Restart=on-failure
User=arduino

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now qclaw-gateway
```

The first inbound message pays the cold model-load cost (3–18 min depending on engine, including prefill of the ~16K-char system prompt); follow-up messages skip that entirely because the llama-server child stays resident. To **warm the page cache at boot** before the first inbound message, drop a short oneshot service that runs `cat ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf > /dev/null` before `qclaw-gateway` starts.

The `ExecStopPost` is important: if the gateway crashes or is restarted, the orphaned llama-server child will keep the port bound and block the next gateway start. Stale-server cleanup details: see `docs/benchmarks/run7/yzma-optimized-benchmark.md`.

---

## Troubleshooting

**"Asking QClaw..." appears on Telegram but no response arrives**

1. Confirm the engine binary is executable: `ls -la engines/yzma/lib/llama-server` must be `-rwxr-xr-x`.
2. Confirm the model is present: `ls -la ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf`.
3. Manually start the configured engine to surface its stderr:
   ```bash
   LD_LIBRARY_PATH=engines/yzma/lib engines/yzma/lib/llama-server \
     -m ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf \
     --host 127.0.0.1 --port 8083 -t 4 -c 8192 -np 1 \
     --reasoning off --jinja
   # In another shell:
   curl -s http://127.0.0.1:8083/health    # expect {"status":"ok"}
   ```
   If the server segfaults, prints `Unsupported GPU`, or never reaches `HTTP server listening`, the binary or GGUF is the problem (not the agent loop).
4. Check the port isn't already taken: `ss -tlnp | grep -E "808[0-3]"` — the provider does not coexist with another process on the same port. Kill stale servers: `pkill -f llama-server`.
5. Run the agent with debug logging: `./build/qclaw gateway --debug` — every spawn logs the full argv, port, and lib_path.
6. Confirm `request_timeout` in `~/.qclaw/config.json` is `1200` — the default 30 s times out during cold model load. Cold spawns take 3–18 min depending on engine; warm follow-ups are seconds.

**Responses are very slow (> 60 seconds on a follow-up turn — not the cold start)**

- Confirm `/no_think` is the first line of `~/.qclaw/workspace/SOUL.md` — without it, Qwen3 generates reasoning tokens before every response, adding 30–120 s. The `--reasoning off` flag (pinned by the provider) is a backup; `/no_think` is the primary suppressor.
- Confirm `parallel: 1` in the engine's `extra_body`. If it's missing or set to `auto`, the server splits ctx across multiple slots and you'll see `"Context size has been exceeded"` HTTP 500 errors. The provider defaults to `WithParallel(1)`; this is only a problem if you explicitly override it.
- Check RAM: `free -h` — yzma's llama-server with `--mlock` pins ~490 MB resident. Two engines on different ports don't share KV cache; the second one will compete with the first.
- Check that page cache has the model: `vmtouch ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf` (install with `apt install vmtouch`) — if 0 % is resident, the next cold call will pay the full mmap cost on eMMC.

**`"Context size has been exceeded"` HTTP 500**

This always means `ctx_size / parallel_slots < (system_prompt + user_message + generation_budget)`. Either set `parallel: 1` in the engine's `extra_body` (provider default) or bump `ctx_size` to `8192 × N` if you really want N slots. The root-cause analysis is in `docs/benchmarks/run7/yzma-optimized-benchmark.md`.

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

Target numbers for the QClaw-v2 `llamaserver` track on `Qwen_Qwen3.5-0.8B-Q4_0`, `-c 8192 -t 4 -np 1 --reasoning off --jinja`, `/no_think` active in `SOUL.md` (pwm_pins prompt, Run 6 + Run 7):

| Engine | Wall (cold) | Notes |
|---|---|---|
| `yzma` ⭐ baseline | **11m49.6s** | Fastest; CPU ARMv8.0 |
| `yzma` + study-bible flags | 12m43.2s | +53 s cold regression; better on warm steady-state |

For warm follow-ups within the same QClaw process, the persistent server stays up so subsequent turns skip the cold model load entirely — only prefill (system prompt + new user turn) and decode are paid.

To reproduce the engine comparison end-to-end:

```bash
# Cold start every time: clear sessions + kill any persistent server first
pkill -f llama-server
rm -f ~/.qclaw/workspace/sessions/*

time qclaw direct --model yzma -m "Which pins on the Uno Q can do PWM?"
```

The full benchmark history is in [`docs/benchmarks/BENCHMARK_SUMMARY.md`](../../benchmarks/BENCHMARK_SUMMARY.md).
