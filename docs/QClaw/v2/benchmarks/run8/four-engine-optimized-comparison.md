# Run 8 — Four-Engine Optimized Comparison

**Hardware:** Arduino Uno Q · Qualcomm QRB2210 · 4× Cortex-A53 · 4 GB LPDDR4X
**Model:** `Qwen_Qwen3.5-0.8B-Q4_0.gguf` (490 MB, Q4_0)
**Prompt:** `"Which pins on the Uno Q can do PWM?"` (pwm_pins, 10 input tokens)
**Date:** 2026-05-25
**Provider:** QClaw-v2 `llamaserver.Provider` via `qclaw direct --model <engine>`

All four engines configured with the same study-bible optimization flag set passed through the
generic `extra_args` mechanism in `extra_body`:

```
--flash-attn on
--mlock
--cache-type-k q8_0
--cache-type-v q8_0
--reasoning-budget 800
```

Plus `-np 1` / `-c 8192` defaults from the provider.

---

## Results Table

| Engine | Wall | Exit | Response | vs unoptimized (prior run) |
|---|---|---|---|---|
| **assix-mpu** ⭐ | **12m35.1s** | 0 ✅ | 241 chars | **−5m19s** (−30%) vs Run 6 (17m54s) |
| **yzma** | 12m58.1s | 0 ✅ | 221 chars | +1m09s (+10%) vs Run 7 baseline (11m49.6s) |
| surgical | 36s | 1 ❌ | EOF | crash @ 36s vs crash @ 57s in Run 6 — flags didn't fix OpenCL `GGML_ASSERT(0)` |
| assix-adreno | 5m00s (timeout) | 124 ⏱ | none | hung at OpenCL kernel compile — same `sub_group_reduce_add` failure as Run 6; binary doesn't support optimization flags anyway |

---

## Headline Finding: The Optimization Flag Order Inverts

Before Run 8, the engine ranking on cold pwm_pins was:

| Run | Engine | Wall | Notes |
|---|---|---|---|
| 6 | assix-mpu (no flags) | 17m54s | CPU fallback |
| 7 | **yzma (no flags except -np 1)** | **11m49.6s** | Fastest |
| 7 | yzma (full opt flags) | 12m43.2s | +53s regression on cold |

After Run 8 (all engines with the same flag set):

| Run | Engine | Wall | Δ vs unoptimized |
|---|---|---|---|
| 8 | **assix-mpu (full opt flags)** | **12m35.1s** | **−5m19s** (huge speedup) |
| 8 | yzma (full opt flags) | 12m58.1s | +69s (slight regression) |

**Yzma was the fastest engine before optimization. assix-mpu is the fastest after optimization.**
The flags help assix-mpu dramatically and hurt yzma slightly — they invert the ranking.

### Why the flags help assix-mpu but hurt yzma

| Factor | assix-mpu (aca9a0f, 16 MB static) | yzma (b9127, 9 MB dynamic) |
|---|---|---|
| llama.cpp version | aca9a0f (older) | a9883db8 / b9127 (newer) |
| linkage | static (all backends in one ELF) | dynamic (separate `.so` files) |
| CPU dispatch | armv8.0 baked in | armv8.0 selected at runtime from 8 build variants |
| flash-attn impl | classic implementation | newer impl with armv8 SIMD intrinsics |
| mlock behavior | locks the whole 16 MB ELF + model | locks model + each `.so` it touches |

Best hypothesis: yzma's newer llama.cpp already includes the optimizations that flash-attn was
designed to provide — when you turn the flag on, you pay for a code-path switch that yields the
same arithmetic. assix-mpu's older build genuinely benefits from the alternative kernel. The
mlock cost is borne by both, but on yzma it's net negative.

---

## Optimized Engine Ranking

| Rank | Engine | Wall | Response quality |
|---|---|---|---|
| 1 ⭐ | **assix-mpu optimized** | **12m35.1s** | Full, structured |
| 2 | yzma optimized | 12m58.1s | Slightly truncated (cut at 221 chars) |
| 3 | surgical optimized | crash @ 36s | EOF (OpenCL GGML_ASSERT) |
| 4 | assix-adreno | hung | OpenCL kernel compile failure |

---

## Untouched: assix-adreno

The assix-adreno binary (`engines/llamacli/llama.cpp/build-adreno/bin/llama-server`) does not
support any of the five optimization flags — its `--help` returns no matching entries. It also
remains blocked at OpenCL kernel compile (`sub_group_reduce_add` undefined on rusticl), so the
flag question is moot until the kernel-source issue is fixed upstream.

---

## Config Changes In This Run

In both `config/qclaw.config.json` and `~/.qclaw/config.json`:

| Engine | Added |
|---|---|
| assix-mpu | `parallel: 1` + 5-flag `extra_args` array |
| surgical | `parallel: 1` + 5-flag `extra_args` array |
| assix-adreno | (none — binary doesn't support the flags) |
| yzma | (already had them since Run 7) |

No Go code changes — the `extra_args` passthrough added in Run 7 handles this generically.

---

## Implications

1. **Production switch:** `assix-mpu` should be marked the default. Update `agents.defaults.model_name`
   to `assix-mpu` in both configs (no change needed — it already is the default; just confirm).
2. **Yzma's role:** Use yzma as the secondary engine — useful when assix-mpu fails, when you want
   a newer llama.cpp, or for testing. Don't ship it as the default given Run 8's data.
3. **Re-benchmark on a different prompt:** This is one cold sample on one prompt. The yzma → assix
   inversion needs at least 2–3 prompt reruns to confirm it's not noise.
4. **Surgical/Adreno:** Blocked by the rusticl `cl_khr_subgroups` issue, not by flag configuration.
   No further config tuning will help — needs a llama.cpp source patch or a different OpenCL stack.
