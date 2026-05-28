# Run 7 — Yzma Engine Integration + Study-Bible Optimization Pass

**Hardware:** Arduino Uno Q · Qualcomm QRB2210 · 4× Cortex-A53 · 4 GB LPDDR4X
**Model:** `Qwen_Qwen3.5-0.8B-Q4_0.gguf` (490 MB, Q4_0)
**Prompt:** `"Which pins on the Uno Q can do PWM?"` (pwm_pins, 10 input tokens)
**Date:** 2026-05-25
**Provider path:** QClaw-v2 `llamaserver.Provider` → `qclaw direct --model yzma`

This run integrates **yzma** (`hybridgroup/yzma` main, b9127 / llama.cpp a9883db8) as QClaw-v2's fourth
engine and benchmarks it in two configurations:

1. **Baseline** — minimal flags (parallel=1 fix applied, no other tuning)
2. **Optimized** — five flags from the architecture study bible added via the new `extra_args` mechanism

---

## Code Changes in This Run

| File | Change |
|---|---|
| `.gitmodules` / `yzma/` | Added `hybridgroup/yzma` as git submodule on QClaw-v2 (mirrors main branch layout) |
| `pkg/providers/llamaserver/provider.go` | Added `parallel int` field, `WithParallel(n)` option, `-np` flag injected into server args. Default set to `1` to prevent the auto-slot split that caused the first run's ctx overflow. |
| `pkg/providers/factory_provider.go` | Wired `extra_body["parallel"]` → `WithParallel`. Added `extra_body["extra_args"]` → `WithExtraArgs` passthrough: parses a JSON `[]string` and appends verbatim to the server command. |
| `config/qclaw.config.json` | Added `yzma` entry: port 8083, lib_path `/home/arduino/ArduinoApps/yzma/lib`, optimized `extra_args`. |
| `~/.qclaw/config.json` | Same (runtime config, not in repo). |

### Root-cause: first run context overflow

The very first yzma run (16m24s, exit 1) failed with `"Context size has been exceeded"`. Diagnosis:
yzma's llama-server b9127 defaults `--parallel` to `-1 = auto`, which on this build auto-selected
**4 KV slots**, dividing the 8192 ctx into **2048 tokens per slot**. The QClaw system prompt
(SOUL.md + IDENTITY.md + pre-router skills inline = ~1500 tokens) plus generation budget exceeded
the per-slot limit. Fix: default `parallel = 1` in the provider struct; all engines now reliably
receive `-np 1` unless explicitly overridden.

---

## Results

### 1. Baseline — `parallel=1`, no other flags

| Pass | Wall time | Response | Exit |
|---|---|---|---|
| Cold (22:55 → 23:06) | **11m49.6s** | 241 chars ✅ | 0 |
| Warm* (23:07 → 23:30) | 22m50.3s ⚠ | 294 chars ✅ | 0 |

*Warm pass is contaminated: two defunct `llama-server` processes (leftover from a prior session
collision) were still reaping during this run, competing for CPU/memory. The `11m49.6s` cold figure
is the reliable baseline.

**Server command (baseline):**
```
/home/arduino/ArduinoApps/yzma/lib/llama-server
  -m ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf
  --host 127.0.0.1 --port 8083
  -t 4 -c 8192 -np 1
  --reasoning off --jinja --log-disable
```

**Cold response:**
> Based on the `sketch-patterns` reference, the pins marked with a tilde (~) are PWM-capable.
> The PWM-capable pins on the Uno Q are: **D3, D5, D6, D9, D10, D11**
> These pins are used for PWM control (e.g., Servo, Servo, PWM, PWM, PWM, PWM).

### 2. Optimized — study-bible flags

**Server command (optimized):**
```
/home/arduino/ArduinoApps/yzma/lib/llama-server
  -m ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf
  --host 127.0.0.1 --port 8083
  -t 4 -c 8192 -np 1
  --reasoning off --jinja --log-disable
  --flash-attn on
  --mlock
  --cache-type-k q8_0 --cache-type-v q8_0
  --reasoning-budget 800
```

| Pass | Wall time | Response | Exit |
|---|---|---|---|
| Cold (03:19 → 03:32) | **12m43.2s** | 146 chars ✅ | 0 |

**Optimized cold response:**
> Based on the `uno-q-hardware` reference, the pins that can do PWM are:
> **D3, D5, D6, D9, D10, D11**
> These are marked with `~` on the silkscreen.

**Finding:** Optimized cold (12m43s) is **53s slower than baseline cold (11m49.6s)** — a ~7.5%
regression. The expected ~10% flash-attn speedup did not materialise on this ARM build. Likely
causes:

- `--mlock` forces all model pages into RAM at load time rather than mmap-on-access (lazy), paying
  a higher upfront cost on a cold run. On a warm run this cost is already paid.
- `--flash-attn on` on this ARM CPU backend (armv8.0 dispatch) may not have a fused QK-V kernel
  that outpaces the scalar path; the overhead of the different code path negates any savings.
- `--cache-type-k/v q8_0` adds per-token quantization cost during KV writes; at 8192 ctx and
  1 slot this is modest but non-zero.

The optimized response (146 chars) is notably more concise than the baseline (241 chars) — both
correct, and the shorter answer is actually higher quality (pins listed cleanly, silkscreen note
added).

---

## Comparison with Previous Runs

| Engine | Config | Wall (cold) | Notes |
|---|---|---|---|
| assix-mpu (Run 6) | static 16 MB, CPU fallback | 17m54s | OpenCL dropped at init |
| surgical (Run 6) | dynamic 9.8 MB, ggml-org | crash @ 57s | GGML_ASSERT in compat decode |
| assix-adreno (Run 6) | dynamic 9.8 MB, Adreno kernels | hung (killed) | `sub_group_reduce_add` undeclared on rusticl |
| **yzma baseline (Run 7)** | dynamic 9.0 MB, RPC+CPU | **11m49.6s** | Correct answer, clean exit |
| **yzma optimized (Run 7)** | + flash-attn, mlock, q8_0 KV, reasoning-budget 800 | **12m43.2s** | 146 chars ✅ |

**Headline finding:** Yzma baseline (11m49.6s) is **6m04s faster than assix-mpu** (17m54s, Run 6)
on the same prompt and model — both CPU-only, clean exit. The yzma b9127 build is the fastest viable
engine tested to date on the Uno Q.

**Optimization flag verdict:** The study-bible flag set produced a **53s regression** on a cold run.
The mlock upfront-load cost and flash-attn ARM-path overhead outweigh any decode savings at cold.
These flags are better candidates for a persistent-server warm path where mlock cost is already
amortised — a warm benchmark with the optimized config is the logical next step.

---

## Flag Rationale (from `docs/QClaw/development/architecture-study-bible.md`)

| Flag | Expected effect | Measurable signal |
|---|---|---|
| `--flash-attn on` | ~10% speedup, lower KV memory pressure via fused QK-softmax-V kernel | Wall time reduction |
| `--mlock` | Pins model weights in RAM; eliminates OS page-out under memory pressure | Consistent cold timing; no swap spikes |
| `--cache-type-k q8_0` / `--cache-type-v q8_0` | Quantizes KV cache to Q8_0 (~halves KV RAM from fp16 to int8) | Allows larger ctx or more headroom for other processes |
| `--reasoning-budget 800` | Belt-and-braces cap on `<think>` tokens; SOUL.md `/no_think` is the primary suppressor | Prevents runaway reasoning on ambiguous prompts |

---

## Backend Detection (stderr)

Baseline cold run stderr (stripped of spinner noise):
```
load_backend: loaded RPC backend from /home/arduino/ArduinoApps/yzma/lib/libggml-rpc.so
load_backend: loaded CPU backend from /home/arduino/ArduinoApps/yzma/lib/libggml-cpu-armv8.0_1.so
```

No OpenCL or Vulkan backend loaded — consistent with the hybridgroup/yzma distribution which
ships CPU + RPC only. GPU path not available on this binary.
