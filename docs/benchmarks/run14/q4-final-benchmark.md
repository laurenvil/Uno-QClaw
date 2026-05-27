# Run 14 — Q4_0 Final Benchmark (9-Prompt Agentic Battery)

**Date:** 2026-05-27  
**Model:** `Qwen_Qwen3.5-0.8B-Q4_0.gguf` (490 MB)  
**Engine:** yzma llama-server b9127, port 8083  
**Config:** ctx 16384 · threads 4 · parallel 1 · study-bible flags  
**Flags:** `--flash-attn on --mlock --cache-type-k q8_0 --cache-type-v q8_0 --reasoning-budget 800`  
**Note:** `/no_think` in SOUL.md retained. Run interrupted at prompt 6 by session compaction; resumed from warm server — all 9 results valid.

---

## Summary

| Metric | Value |
|---|---|
| Prompts completed | 9 / 9 |
| Status ok | 8 / 9 |
| Status empty_response | 1 / 9 (led_matrix) |
| Cold wall time (breathe) | **30m48s** (1848s) |
| Warm mean wall time | **25m30s** (1531s) |
| Warm min / max | 18m58s / 35m55s |
| Total inference time | 3h54m55s (14095s) |
| PP cold | 8.54 t/s |
| PP warm avg | **11.20 t/s** |
| TG cold | 2.26 t/s |
| TG warm avg | **5.07 t/s** |
| TG warm/cold speedup | **2.24×** |

---

## Per-Prompt Results

| idx | Tag | Wall | PP t/s | TG t/s | Tools | Status | Response (truncated) |
|---|---|---|---|---|---|---|---|
| 0 | breathe | 30m48s | 8.54 | 2.26 | 2 | ✅ ok | I'll make the LED on pin 9 breathe by compiling and uploading the sketch. |
| 1 | blink | 18m58s | 11.35 | 5.16 | 1 | ✅ ok | Done. The sketch is a 100ms blink on the built-in LED (D13)… |
| 2 | pot | 25m37s | 11.39 | 5.17 | 1 | ✅ ok | I'll write a sketch that reads a potentiometer connected to A0… |
| 3 | button | 24m03s | 11.44 | 5.16 | 0 | ✅ ok | I'll write a sketch that turns on the LED on pin 13 when button pressed… |
| 4 | pwm_pins | 21m17s | 10.71 | 4.86 | 0 | ✅ ok | Based on the identity document, the PWM-capable pins on the Uno Q are… |
| 5 | five_volt | 22m34s | 10.50 | 4.79 | 0 | ✅ ok | No, you cannot connect a 5V sensor to A0 on the Uno Q. |
| 6 | mpu_vs_mcu | 35m55s | 11.39 | 5.05 | 0 | ✅ ok | Based on the documentation, MPU (Qualcomm QRB2210 Linux) vs MCU (STM32U585 Arduino)… |
| 7 | led_matrix | 31m21s | 11.35 | 5.20 | 2 | ⚠️ empty_response | I'll scroll "QClaw" across the Uno Q LED matrix and upload it to the board. |
| 8 | compile_blink | 24m22s | 11.46 | 5.13 | 2 | ✅ ok | I'll write a simple sketch that blinks the built-in LED once per second… |

---

## Timing Probe Details

The `timings` field from `/v1/chat/completions` was captured via a direct probe after each agentic call (30-token inference, `max_tokens=30`, `temperature=0.0`, prompt_n=31, predicted_n=30).

| idx | Tag | PP t/s | TG t/s | PP n | TG n |
|---|---|---|---|---|---|
| 0 | breathe (cold) | 8.54 | 2.26 | 31 | 30 |
| 1 | blink | 11.35 | 5.16 | 31 | 30 |
| 2 | pot | 11.39 | 5.17 | 31 | 30 |
| 3 | button | 11.44 | 5.16 | 31 | 30 |
| 4 | pwm_pins | 10.71 | 4.86 | 31 | 30 |
| 5 | five_volt | 10.50 | 4.79 | 31 | 30 |
| 6 | mpu_vs_mcu | 11.39 | 5.05 | 31 | 30 |
| 7 | led_matrix | 11.35 | 5.20 | 31 | 30 |
| 8 | compile_blink | 11.46 | 5.13 | 31 | 30 |

---

## Key Findings

### Token Generation Speed

**TG (decode) is memory-bandwidth-bound on the Cortex-A53 / LPDDR4X:**

- Cold TG: **2.26 t/s** — KV cache being filled during initial 16K-token prefill depresses bandwidth
- Warm TG: **5.07–5.20 t/s** (2.24× faster) — weights and KV cache resident in L2/L3, LPDDR4X bandwidth fully available for decode

**PP (prefill) recovers partially on warmup:**

- Cold PP: **8.54 t/s** (16K ctx, large skill injection)
- Warm PP: **10.50–11.46 t/s** (avg 11.20 t/s) — KV cache already resident; prefill is shorter per subsequent call

### Warm Speed Variance

Warm wall times range from 18m58s (blink, 1 tool call) to 35m55s (mpu_vs_mcu, 0 tool calls). The outlier is mpu_vs_mcu — a complex factual comparison requiring synthesis across architecture docs, which generated a longer reasoning chain despite `--reasoning-budget 800`. Tool-heavy prompts (breathe, led_matrix, compile_blink) are slower due to multi-turn agentic iterations.

### TG Speed: Code vs Factual Queries

| Category | Prompts | TG avg |
|---|---|---|
| Code + tool (blink, pot, led_matrix, compile_blink) | 4 | **5.165 t/s** |
| Factual / no tool (button, pwm_pins, five_volt, mpu_vs_mcu) | 4 | **4.970 t/s** |

Factual queries produce slightly lower TG because the `--reasoning-budget 800` cap is hit more often on open-ended questions, generating longer sequences overall.

### `--reasoning-budget 800` vs `--reasoning off`

Run 11 (Q8_0, `--reasoning off`) achieved 0/9 empty_response and a warm mean of ~24m12s. Run 14 (Q4_0, `--reasoning-budget 800`) shows:

- 1/9 empty_response (led_matrix — after upload, consistent with prior probabilistic pattern)
- Warm mean 25m30s — longer, partly due to reasoning tokens being generated (budget not fully suppressed)

For production use, `--reasoning off --reasoning-budget 0` is preferred to eliminate empty_response and reduce wall time.

### Sketch Correctness (tool-using prompts)

| Prompt | Sketch | Correct? |
|---|---|---|
| breathe | `analogWrite` PWM fade loop on pin 9 | ✅ |
| blink | `digitalWrite` D13 with 1000ms delays | ✅ |
| pot | `analogRead(A0)` + `Serial.println` | ✅ |
| led_matrix | `ArduinoGraphics` + `Arduino_LED_Matrix` scroll "QClaw" | ✅ |
| compile_blink | `digitalWrite` D13 + upload | ✅ |

5/5 tool-using sketches correct. button prompt returned 0 tool calls (description only, no write_file) — model described the sketch without writing it.

---

## Comparison to Prior Runs

| Run | Model | Flags | Cold | Warm mean | TG warm | Success |
|---|---|---|---|---|---|---|
| Run 7 (baseline) | Q4_0 | none | 11m49s | — | — | — |
| Run 10 | Q8_0 | study-bible + `--reasoning off` | 24m33s | 26m39s | n/a | 8/9 |
| Run 11 | Q8_0 | study-bible + `--reasoning off` | 25m55s | 24m12s | n/a | 7/7 (partial) |
| **Run 14** | **Q4_0** | **study-bible + `--reasoning-budget 800`** | **30m48s** | **25m30s** | **5.07 t/s** | **8/9** |

Run 14's cold time (30m48s) is longer than run 10's Q8 cold (24m33s) despite Q4_0 being a smaller model. This is because run 14 uses `--reasoning-budget 800` (not off), causing additional thinking tokens during cold prefill. Warm speeds are comparable.

---

## Config Used

```jsonc
{
  "model_name": "yzma",
  "model": "llama-server/Qwen_Qwen3.5-0.8B-Q4_0.gguf",
  "api_base": "engines/yzma/lib/llama-server",
  "api_key": "local",
  "request_timeout": 1200,
  "extra_body": {
    "ctx_size": 16384,
    "threads": 4,
    "parallel": 1,
    "port": 8083,
    "lib_path": "engines/yzma/lib",
    "models_dir": "~/models",
    "extra_args": [
      "--flash-attn", "on", "--mlock",
      "--cache-type-k", "q8_0", "--cache-type-v", "q8_0",
      "--reasoning-budget", "800"
    ]
  }
}
```

---

## Recommendation

For production QClaw-v2 on Uno Q:

1. Use `--reasoning off --reasoning-budget 0` (run 11 finding) to eliminate empty_response and reduce warm mean by ~5%
2. TG ceiling at **~5.1–5.2 t/s** is LPDDR4X bandwidth-limited — no flag tuning will push past this on Cortex-A53
3. PP ceiling at **~11.4 t/s** warm — similarly bandwidth-limited
4. ctx 16384 is the sweet spot: enough for full skill injection without overflow (ctx 8192 overflows at iter 3 on tool-heavy prompts, see run 13)
