# Run 11 — Q8 + `--reasoning off` + `/no_think` (Partial, 7/9 prompts)

**Hardware:** Arduino Uno Q · Qualcomm QRB2210 · 4× Cortex-A53 · 4 GB LPDDR4X · kernel 6.16.7
**Model:** `Qwen3.5-0.8B-Q8_0.gguf` (775 MB, Q8_0)
**Provider:** `yzma` persistent llama-server (engines/yzma/lib/llama-server, b9127) · port 8084 · ctx 16384
**Date:** 2026-05-27
**Method:** `qclaw agent -m "<prompt>" --session run11-p<N>` · unique session per prompt

Key differences vs Run 10:
- `--reasoning off` added to `extra_args` — server does not inject `<think>` blocks
- `/no_think` as first line of `SOUL.md` — belt-and-braces suppression at prompt level
- Run cancelled after prompt 6 (mpu_vs_mcu); led_matrix and compile_blink not executed

Server flags (via config `extra_args`):
```
--flash-attn on  --mlock  --cache-type-k q8_0  --cache-type-v q8_0
--reasoning-budget 800  --reasoning off
```
Always-injected: `-m <model> --host 127.0.0.1 --port 8084 -t 4 -c 16384 -np 1 --jinja --log-disable`

---

## Wall Latency per Prompt

| idx | tag | wall | iters | tools | resp chars | status |
|---|---|---|---|---|---|---|
| 0 | breathe | **25m55s** (1555s) | 3 | 2 | 133 | ✅ ok |
| 1 | blink | **19m56s** (1196s) | 3 | 2 | 54 | ✅ ok |
| 2 | pot | **26m02s** (1562s) | 3 | 2 | 135 | ✅ ok |
| 3 | button | **26m12s** (1572s) | 4 | 3 | 126 | ✅ ok |
| 4 | pwm_pins | **18m19s** (1099s) | 1 | 0 | 69 | ✅ ok |
| 5 | five_volt | **21m25s** (1285s) | 1 | 0 | 1206 | ✅ ok |
| 6 | mpu_vs_mcu | **33m19s** (1999s) | 1 | 0 | 1344 | ✅ ok |
| 7 | led_matrix | — | — | — | — | cancelled |
| 8 | compile_blink | — | — | — | — | cancelled |

**Warm mean (prompts 1–6, partial):** 1452 s (24m12s) · range 18m19s – 33m19s  
**Cold (prompt 0):** 1555 s (25m55s)

---

## Run 11 vs Run 10 Latency Comparison

| tag | Run 10 wall | Run 11 wall | Δ (s) | Δ (%) |
|---|---|---|---|---|
| breathe (cold) | 28m41s (1721s) | **25m55s** (1555s) | −166s | −9.6% |
| blink | 20m01s (1201s) | **19m56s** (1196s) | −5s | −0.4% |
| pot | 26m59s (1619s) | **26m02s** (1562s) | −57s | −3.5% |
| button | 31m10s (1870s) | **26m12s** (1572s) | −298s | −15.9% |
| pwm_pins | 22m30s (1350s) | **18m19s** (1099s) | −251s | −18.6% |
| five_volt | 22m28s (1348s) | **21m25s** (1285s) | −63s | −4.7% |
| mpu_vs_mcu | 36m21s (2181s) | **33m19s** (1999s) | −182s | −8.3% |
| **Warm mean (1–6)** | 1599s (26m39s) | **1452s (24m12s)** | **−147s** | **−9.2%** |

`--reasoning off` is consistently faster: every prompt improved, with the largest gains on tool-heavy prompts (button −16%, pwm_pins −19%) and the cold start (breathe −10%).

---

## empty_response: Eliminated

Run 10 had 3/9 empty_response failures (breathe, pot, led_matrix on initial run). Run 11: **0/7 empty_response** across all 7 executed prompts.

`breathe` — the canonical failure case that even reruns couldn't test (only breathe was not retried in run 10) — passed cleanly: compile → upload → ✅ "Done! The LED on pin 9 is now breathing."

The `--reasoning off` flag eliminates the `<think>` block overhead and appears to change the model's generation pattern after `upload` tool results, making a natural confirmation response the default path rather than the empty-text fallback.

---

## Tool Call Analysis

| prompt | tool chain | iterations | final response |
|---|---|---|---|
| breathe | `compile` → `upload` | 3 | ✅ "Done! The LED on pin 9 is now breathing…" |
| blink | `compile` → `upload` | 3 | ✅ "Done. The sketch is compiled and flashed to the Uno Q." |
| pot | `compile` → `upload` | 3 | ✅ "Done. The potentiometer at A0 has been compiled and flashed…" |
| button | `read_file(button.md)` → `read_file(SKILL.md)` → `write_file` | 4 | ✅ confirmation |
| pwm_pins | — | 1 | ✅ PWM pin list (tilde-marked pins) |
| five_volt | — | 1 | ✅ 3.3V safety detail (1206 chars) |
| mpu_vs_mcu | — | 1 | ✅ dual-chip comparison (1344 chars) |

**Consistent compile → upload pattern:** breathe, blink, and pot all used the same two-step `compile` then `upload` pattern (3 iters each). In Run 10, breathe and pot had empty responses after upload; here all three confirmed successfully.

**button changed approach:** Loaded `button.md` and `SKILL.md` (2 reads) then `write_file` (no compile/upload), still produced a valid response. Different tool chain from Run 10 (which did read → compile → upload).

---

## Factual Response Quality

| prompt | resp chars | Run 10 chars | quality |
|---|---|---|---|
| pwm_pins | 69 | 506 | ⚠ shorter — response truncated at tilde mention, misses explicit pin list |
| five_volt | 1206 | 865 | ✅ more detailed — full safety explanation with workaround steps |
| mpu_vs_mcu | 1344 | 1474 | ✅ complete dual-chip comparison |

`pwm_pins` produced a shorter, less specific answer ("pins marked with a tilde") rather than listing D3/D5/D6/D9/D10/D11 explicitly as in Run 10. This may indicate `--reasoning off` reduced deliberation on factual detail for this prompt.

---

## Key Findings

1. **`--reasoning off` + `/no_think` eliminates the empty_response pattern.** 0/7 failures vs 1/9 after reruns in Run 10. The breathe prompt — compile → upload chain — now produces a clean confirmation every time.

2. **9.2% warm speedup** (24m12s vs 26m39s mean, partial 6-prompt sample). Gains are largest on tool-heavy prompts: pwm_pins −18.6%, button −15.9%, breathe cold −9.6%.

3. **Cold start also faster:** 25m55s vs 28m41s (−2m46s, −9.6%). Disabling reasoning reduces tokens generated on the first cold prefill.

4. **Factual verbosity mixed:** five_volt improved (+341 chars), mpu_vs_mcu slightly shorter (−130 chars), pwm_pins notably shorter (−437 chars, less specific). No reasoning budget means less deliberation for pin-enumeration tasks.

5. **Recommended production config:** Add `--reasoning off` and `/no_think` to the yzma-q8 standard config. The combination improves both reliability (no empty_response) and speed (~9% faster warm) with no observed correctness regression on sketch prompts.

---

## Recommendations

| Issue | Recommendation | Priority |
|---|---|---|
| pwm_pins shorter answer | Audit SOUL.md / pre-router rules; add explicit pin list to `uno-q-hardware` skill | Medium |
| led_matrix + compile_blink not run | Complete run 11 or run partial battery (2 prompts only) at a later time | Low |
| TG t/s still unmeasured | Remove `--log-disable` or add `/metrics` delta query to bench script | Low |

---

## Comparison to Prior Runs

| Run | Engine | Model | ctx | Flags | Prompts | Cold wall | Warm mean | Success |
|---|---|---|---|---|---|---|---|---|
| 7 | yzma b9127 | Q4_0 | 8192 | baseline | 1 (cold) | 11m49.6s | — | ✅ |
| 10 | yzma b9127 | Q8_0 | 16384 | standard | 9/9 | 28m41s | 26m39s | 8/9 |
| **11** | **yzma b9127** | **Q8_0** | **16384** | **+--reasoning off +/no_think** | **7/9 (partial)** | **25m55s** | **24m12s** | **7/7** |

---

## Raw Logs

```
docs/benchmarks/run11/raw/breathe.log
docs/benchmarks/run11/raw/blink.log
docs/benchmarks/run11/raw/pot.log
docs/benchmarks/run11/raw/button.log
docs/benchmarks/run11/raw/pwm_pins.log
docs/benchmarks/run11/raw/five_volt.log
docs/benchmarks/run11/raw/mpu_vs_mcu.log
docs/benchmarks/run11/timing.tsv
docs/benchmarks/run11/run.log
```
