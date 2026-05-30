# Run 17 — llamacli-mpu Full 9-Prompt Agentic Battery

**Date:** 2026-05-29  
**Model:** `Qwen_Qwen3.5-0.8B-Q4_0.gguf` (490 MB)  
**Engine:** `engines/llamacli/mpu/llama-server` (e6ed0a2, GPU-CLI noshuffle build, static 16 MB)  
**Source:** `assix/Arduino-UnoQ-Optimized-Llama-CLI` branch `QClaw-GPU-CLI`  
**Config:** ctx 9000 · threads 4 · parallel 1 · port 8086  
**Flags:** `--flash-attn on --mlock --cache-type-k q8_0 --cache-type-v q8_0 --reasoning-budget 800 --repeat-penalty 1.1 --repeat-last-n 64`  
**Script:** `scripts/bench-run17-mpu.sh`

---

## Context: Why This Engine

Runs 15 and 16 drove the choice of `llamacli-mpu`:

- **Run 15** (yzma, ctx 9000): KV cache saturated at prompt 2. TG collapsed from 5.13 → 0.92 t/s on the pot prompt, then prompts 3–8 all exited in 0s with error(1). Root cause: ctx 9000 is too small for yzma's session accumulation on multi-tool prompts. yzma's llama.cpp b9127 may handle cumulative session state differently from older builds.
- **Run 16** (llama-wang engine): Crashed at prompt 0 after 37s with `GGML_ASSERT(0)`. Root cause: Mesa rusticl on the QRB2210's FD702 GPU drops `cl_khr_subgroups`, so llama.cpp falls back to the Q4_0 noshuffle kernel path. llama-wang is missing `gemv_noshuffle_q4_0_f32.cl`, `gemv_noshuffle_q4_0_f32_spec.cl`, and `gemm_noshuffle_q4_0_f32.cl` — the three kernels that handle Q4_0 without subgroups.

The `QClaw-GPU-CLI` branch of `assix/Arduino-UnoQ-Optimized-Llama-CLI` adds exactly those three missing kernels. The resulting static binary (`engines/llamacli/mpu/llama-server`, e6ed0a2) uses CPU fallback cleanly (OpenCL init fails at startup due to `sub_group_reduce_add` unavailability, then falls through to CPU-only mode automatically).

---

## Summary

| Metric | Value |
|---|---|
| Prompts completed | 9 / 9 |
| Status ok | **7 / 9** |
| Status empty_response | 1 / 9 (led_matrix) |
| Status error(1) | 1 / 9 (mpu_vs_mcu — ctx overflow) |
| Cold wall time (breathe) | **26m52s** (1612s) |
| Warm mean wall time (7 ok+empty prompts) | **23m27s** (1406s) |
| Warm min / max | 18m48s / 27m14s |
| Total inference time | ~3h27m (12462s) |
| PP warm avg | **11.40 t/s** |
| TG warm avg | **5.09 t/s** |
| PP cold | 10.92 t/s |
| TG cold | 4.82 t/s |

**vs Run 14 (yzma baseline, ctx 16384):**

| Metric | Run 17 (mpu, ctx 9000) | Run 14 (yzma, ctx 16384) | Δ |
|---|---|---|---|
| TG warm avg | **5.09 t/s** | 5.07 t/s | +0.02 t/s (≈ flat) |
| PP warm avg | **11.40 t/s** | 11.20 t/s | +0.2 t/s |
| Cold wall | 26m52s | 30m48s | **−3m56s** |
| Warm mean wall | 23m27s | 25m30s | **−2m03s** |
| Success rate | 7/9 | 8/9 | −1 (ctx overflow) |

The llamacli-mpu binary at ctx 9000 is **~8% faster wall time** on warm prompts than yzma at ctx 16384, primarily because the smaller context window reduces KV prefill cost per turn. TG bandwidth ceiling is identical (~5.1 t/s) — both are LPDDR4X-bound.

---

## Per-Prompt Results

| idx | Tag | Wall | PP t/s | TG t/s | Tools | Status | Response |
|---|---|---|---|---|---|---|---|
| 0 | breathe | 26m52s | 10.92 | 4.82 | 0 | ✅ ok | I'll write an Arduino sketch for LED on pin 9 to breathe smoothly… |
| 1 | blink | 22m29s | 11.48 | 5.14 | 1 | ✅ ok | The sketch has been successfully compiled and flashed to the STM32U585 Uno Q. |
| 2 | pot | 23m55s | 11.50 | 5.11 | 0 | ✅ ok | I'll write a complete Arduino sketch that reads the potentiometer… |
| 3 | button | 27m8s | 11.41 | 5.08 | 1 | ✅ ok | Done. The Arduino sketch has been compiled and flashed to the Uno Q board. |
| 4 | pwm_pins | 18m48s | 11.42 | 5.13 | 0 | ✅ ok | Based on the Uno Q hardware reference, PWM-capable pins are marked with a tilde (`~`)… |
| 5 | five_volt | 22m44s | 11.51 | 5.12 | 0 | ✅ ok | This is a critical safety question! **No, you cannot connect a 5V sensor to A0.** |
| 6 | mpu_vs_mcu | 1s | 8.51 | 4.15 | 0 | ❌ error(1) | *(ctx overflow — see below)* |
| 7 | led_matrix | 27m14s | 11.30 | 5.03 | 1 | ⚠ empty_response | I'll scroll "QClaw" across the Uno Q LED matrix and compile/flash it to the board. |
| 8 | compile_blink | 21m49s | 11.51 | 5.04 | 1 | ✅ ok | I'll write a sketch that blinks the built-in LED once per second and compile it… |

---

## Timing Probe Details

Probe uses a direct `POST /v1/chat/completions` call after each agentic run (31-token prompt, 30-token generation, temperature 0.0). Measures the llama-server's own reported `timings` field.

| idx | Tag | PP t/s | TG t/s | PP n | TG n |
|---|---|---|---|---|---|
| 0 | breathe (cold) | 10.92 | 4.82 | 31 | 30 |
| 1 | blink | 11.48 | 5.14 | 31 | 30 |
| 2 | pot | 11.50 | 5.11 | 31 | 30 |
| 3 | button | 11.41 | 5.08 | 31 | 30 |
| 4 | pwm_pins | 11.42 | 5.13 | 31 | 30 |
| 5 | five_volt | 11.51 | 5.12 | 31 | 30 |
| 6 | mpu_vs_mcu | 8.51 | 4.15 | 31 | 30 |
| 7 | led_matrix | 11.30 | 5.03 | 31 | 30 |
| 8 | compile_blink | 11.51 | 5.04 | 31 | 30 |

PP cold is 10.92 t/s (vs 8.54 in Run 14). The smaller ctx (9000 vs 16384) means less to prefill during cold load — explains the faster cold wall and higher cold PP.

The mpu_vs_mcu probe shows TG dropped to 4.15 t/s and PP to 8.51 t/s — consistent with a request that was rejected at the HTTP layer after the server spent time partially processing it.

---

## Failure Analysis

### mpu_vs_mcu — error(1), ctx overflow

Wall: 1s. The agent exited immediately with `error(1)`. The raw log shows:

```
llama-server returned 400: request (10345 tokens) exceeds the available context size (9216 tokens)
```

The mpu_vs_mcu prompt inlines `uno-q-hardware/SKILL.md` + `pinout.md` + `voltage-safety.md` + the system prompt via the pre-router, totalling **10,345 tokens** — exceeding the 9,216-token KV budget at ctx 9000 (llama-server rounds to the next multiple of 512 = 9216). The server remained healthy; prompts 7 and 8 both succeeded normally after this failure.

**Fix:** raise `ctx_size` to ≥11,000 for this prompt to pass. ctx 11264 (= 22 × 512) would give ~930-token headroom.

### led_matrix — empty_response

Wall: 27m14s. The model ran the full time budget and called the arduino tool once, but returned the `no response to give` sentinel. This is the same pattern observed in Run 14 (led_matrix only) — the matrix scroll prompt generates a large intermediate sketch + compilation output that consumes most of the generation budget before the final text response. Consistent with a per-session context pressure issue, not a model capability failure.

---

## Engine Notes

### Binary provenance

| Item | Value |
|---|---|
| Source repo | `assix/Arduino-UnoQ-Optimized-Llama-CLI` |
| Branch | `QClaw-GPU-CLI` |
| Commit | `e6ed0a2` |
| llama.cpp base | `b9099-5d5d2e15d` |
| Build type | Static (libllama + libggml + OpenCL + CPU), 16 MB |
| Target | aarch64 Linux (Cortex-A53, QRB2210) |

### OpenCL status

The binary includes the three Q4_0 noshuffle kernels that llama-wang was missing:
- `gemv_noshuffle_q4_0_f32.cl`
- `gemv_noshuffle_q4_0_f32_spec.cl`
- `gemm_noshuffle_q4_0_f32.cl`

At startup on the QRB2210, OpenCL initialization fails because Mesa rusticl 25.2.6 does not implement `sub_group_reduce_add` (required by other OpenCL kernels). The binary falls back to CPU automatically. TG performance is therefore pure Cortex-A53 CPU, identical to yzma — the OpenCL path is not active in these results.

Full engine build notes: `engines/llamacli/mpu/BUILD.md`.

---

## Comparison Table: Runs 14, 15, 16, 17

| Run | Engine | ctx | TG warm | Cold wall | Success |
|---|---|---|---|---|---|
| 14 | yzma b9127 | 16384 | 5.07 t/s | 30m48s | 8/9 |
| 15 | yzma b9127 | 9000 | **collapsed** (0.92 t/s by prompt 2) | 25m42s (aborted) | 2/2 before abort |
| 16 | llama-wang | 9000 | N/A (GGML_ASSERT crash) | 37s (crashed) | 0/1 |
| **17** | **llamacli-mpu e6ed0a2** | **9000** | **5.09 t/s** | **26m52s** | **7/9** |

**Key finding:** The llamacli-mpu static binary handles ctx 9000 correctly where yzma b9127 could not. The only failure is the hard 10,345-token mpu_vs_mcu overflow — a deterministic budget problem, not a stability issue. Warm TG is essentially identical to yzma at 16384 (~5.1 t/s LPDDR4X ceiling), but wall time is ~8% faster due to lower prefill cost at the smaller context window.
