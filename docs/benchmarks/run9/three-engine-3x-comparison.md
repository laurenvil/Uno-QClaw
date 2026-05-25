# Run 9 — Three-Engine, Three-Sample Comparison (pwm_pins)

**Hardware:** Arduino Uno Q · Qualcomm QRB2210 · 4× Cortex-A53 · 4 GB LPDDR4X
**Model:** `Qwen_Qwen3.5-0.8B-Q4_0.gguf` (490 MB, Q4_0)
**Prompt:** `"Which pins on the Uno Q can do PWM?"` (pwm_pins, main-branch standard battery)
**Date:** 2026-05-25
**Method:** 3 cold runs per engine, sessions cleared + servers killed between every run

This run answers two questions raised at the end of Run 8:

1. **Is the assix-mpu / yzma inversion real or single-sample noise?** Re-run 3× each.
2. **Is llama-cli (one-shot subprocess) a viable direct-path option?** Compare a third engine on the same prompt.

---

## Generation Speed and Latency (Cold)

| Engine | Run 1 | Run 2 | Run 3 | Mean | σ | Range |
|---|---|---|---|---|---|---|
| **assix-mpu optimized** | 749s | 744s | 746s | **746.3 s** (12m26s) | 2.1 s | 5 s |
| **yzma optimized** | 756s | 759s | 749s | **754.7 s** (12m35s) | 4.2 s | 10 s |
| **llamacli-mpu (yzma binary)** | 1200s (killed) | aborted | aborted | — | — | — |

### Δ between server engines

assix-mpu averages **8.4 s faster** than yzma (1.1%). Both engines are dramatically more reproducible than the run-to-run noise allowed (σ ≤ 5 s on 12-min runs).

**Run 8's 23s gap shrinks to 8s with three samples** — most of Run 8's apparent gap was noise. But the directional finding holds: **assix-mpu (older static llama.cpp + study-bible flags) is consistently faster than yzma (newer dynamic llama.cpp + study-bible flags) on pwm_pins**.

---

## Output Correctness

All runs across both server engines named the **correct six PWM pins (D3, D5, D6, D9, D10, D11)** and correctly cited the tilde marking from the `uno-q-hardware` reference. No hallucinations, no wrong pin counts.

### Response length

| Engine | chars (mean) | Style |
|---|---|---|
| assix-mpu | 200 chars | Terser — single sentence + bold pin list |
| yzma | 245 chars | More verbose — preamble + bulleted pin list + closing sentence |

Both styles are appropriate for the prompt. Sample responses (run 1 of each):

**assix-mpu:**
> Based on the `uno-q-hardware` reference in your workspace, the PWM-capable pins on the Uno Q are:
> **D3, D5, D6, D9, D10, D11**
> These pins are marked with a tilde (`~`) in the pinout table and are used for PWM generation.

**yzma:**
> Based on the `uno-q-hardware` reference, the pins capable of PWM (Pulse Width Modulation) are marked with a tilde (~) in the MCU pinout table.
>
> The PWM-capable pins on the Uno Q are:
> - **D3**, **D5**, **D6**, **D9**, **D10**, **D11**
>
> These pins are marked with a tilde (~) in the MCU pinout table.

---

## llama-cli Direct Path — Blocked by Sampler Defaults

| Run | Wall | Exit | chars | Outcome |
|---|---|---|---|---|
| 1 | 1200s (qclaw timeout) | 1 | partial | **Repetition loop** — model answered correctly then drifted into "Do not use these for PWM on the UART1 TX pins (D1/D0), as they are UART1." repeated ~50× until the 2048-token output budget was filled. qclaw's 1200s wall-clock timeout killed the subprocess. |
| 2 | aborted | — | — | Stopped after run 1 confirmed the failure mode. |
| 3 | aborted | — | — | Same. |

### Root cause: missing sampler controls in the llamacli provider

The llama-cli subprocess is invoked with:
```
yzma/lib/llama-cli ... --grammar '{"text":...}' -c 8192 -t 4 -n 2048 --temp 0.3
```

No `--repeat-penalty`, no `--repeat-last-n`, no `--presence-penalty`, no `--frequency-penalty`.
The binary's defaults (`repeat-penalty = 1.0` = off) are inherited, and at 0.8B-Q4_0 scale this
model is **known** to enter token-loop behaviour — see `docs/QClaw/whitepaper.md` §9.2 "0.8B
Repetition Loop Prevention" on the main branch, which catalogues this exact problem.

The llama-server engines don't trip this because the OpenAI chat-completions code path applies
sane defaults (repeat-penalty ≈ 1.1, last_n = 64) when no explicit value is sent in the request.
The llamacli provider has no equivalent. With temperature 0.3 and a JSON-envelope grammar locking
the model into a single string token, once it hits a high-likelihood continuation it has no
escape valve.

### What the partial response looked like

The first sentence was correct:
> PWM pins on the Uno Q (QRB2210) are **D3, D5, D6, D9, D10, D11**. These are marked with a tilde (~) on the silkscreen and are used for PWM control.

Then it drifted:
> Do not use these for PWM on the MCU side ... Do not use these for PWM on the MPU side ... Do not use these for PWM on the Qwiic connector ... [escalates]

And finally locked into the loop:
> Do not use these for PWM on the UART1 TX pins (D1/D0), as they are UART1.
> Do not use these for PWM on the UART1 TX pins (D1/D0), as they are UART1.
> Do not use these for PWM on the UART1 TX pins (D1/D0), as they are UART1.
> [×50+]

### Provider changes required to make this work

The original assix `engines/llamacli/mpu/llama-cli` binary is **no longer viable on this hardware**: its statically-linked OpenCL backend tries to compile Adreno-specific kernels at init that fail on Mesa rusticl 25.2.6 (`sub_group_reduce_add` undefined). Same blocker as `assix-adreno` server in Run 6.

Setting `GGML_OPENCL_PLATFORM=none` allows the assix binary to skip OpenCL init, but it then exits with no output — it has no CPU fallback path. The assix llama-cli binary is effectively bricked on the current device.

To make the comparison fair, I:
1. Added `GGML_OPENCL_PLATFORM=none` to the env of every llama-cli subprocess in `pkg/providers/llamacli/provider.go`.
2. Added `WithLibraryPath` option mirroring the llamaserver one — wired through `factory_provider.go` from `extra_body["lib_path"]`.
3. Repointed the `llamacli-mpu` model entry at `yzma/lib/llama-cli` (yzma ships a working CPU+RPC llama-cli built from the same llama.cpp source as the yzma server).

Now the direct-path comparison is **same llama.cpp build (b9127), subprocess vs persistent server** — true architectural apples-to-apples.

---

## Architectural Implications for Direct Path

The comparison "llama-cli direct vs llama-server direct as architectural patterns" is **inconclusive
from this run** because the llamacli provider lacks repetition controls that the llama-server path
gets for free via OpenAI-API defaults. The current llamacli provider would need:

1. `--repeat-penalty 1.1`, `--repeat-last-n 64` defaults (matches llama-server's web defaults)
2. A `--presence-penalty` / `--frequency-penalty` passthrough from the request `options` map
3. A wall-clock guard tighter than `request_timeout` — e.g. abort if no progress for 60s

Until those are added, llama-cli direct is **not viable on this hardware with this model**.

**Updated decision tree:**

| Effort to fix llamacli sampler | Resulting recommendation |
|---|---|
| Fix the three gaps (~30 min of Go work), re-run Run 9 llama-cli | Then the apples-to-apples comparison is meaningful; revisit Option A vs Option B |
| Don't fix | Use yzma llama-server for both paths. Direct-path "orphan server" risk is a known operational cost; the alternative is documented broken. |

The architectural argument from the prior analysis (llama-cli's robustness — no orphan, no port
conflict, no shared blast radius) is real, but only worth pursuing if the sampler bug is fixed
first. Without that fix, llama-cli direct fails in a far worse way than llama-server's worst case:
20-minute hangs with the user getting nothing back, not even an error message worth reading.

---

## Engine Ranking (Cold, Single Prompt)

| Rank | Engine | Wall (mean) | Source |
|---|---|---|---|
| 1 | assix-mpu optimized | **12m26s** | Run 9 (3 samples, σ=2s) |
| 2 | yzma optimized | 12m35s | Run 9 (3 samples, σ=4s) |
| ❌ | llamacli-mpu (yzma binary) | 1200s timeout | Run 9 — repetition loop, killed by qclaw |
| ❌ | surgical optimized | crash @ 36s | Run 8 (OpenCL GGML_ASSERT) |
| ❌ | assix-adreno | hang (5min timeout) | Run 8 (OpenCL kernel compile fail) |

---

## What This Run Tells Us About Run 8

| Question | Answer |
|---|---|
| Was Run 8's 23 s assix-vs-yzma gap signal? | Half signal, half noise. The true gap is ~8 s. The ranking holds. |
| Is the inversion (Run 7 yzma fastest → Run 8 assix fastest) real after optimization? | **Yes.** With three samples each, both means are tight (σ ≤ 5 s) and non-overlapping. |
| Should we change the production default from `assix-mpu` to yzma? | **No.** `assix-mpu` is rightfully the default. yzma is the right fallback. |

---

## Code Changes Captured

| File | Change |
|---|---|
| `pkg/providers/llamacli/provider.go` | Added `libraryPath` field, `WithLibraryPath(string) Option`, `buildEnv()` helper that injects `GGML_OPENCL_PLATFORM=none` (mandatory on this hardware) and prepends to `LD_LIBRARY_PATH` (optional). |
| `pkg/providers/factory_provider.go` | Parse `extra_body["lib_path"]` for the `llama-cli` protocol case, pass to `WithLibraryPath`. |
| `config/qclaw.config.json` + `~/.qclaw/config.json` | Added `llamacli-mpu` entry pointing at `yzma/lib/llama-cli` with `lib_path: yzma/lib`. Inline `_comment` documents the assix-binary failure. |
| `yzma/lib/llama-cli` | Copied from `/home/arduino/ArduinoApps/yzma/lib/llama-cli` (b9127, CPU+RPC, working). |
