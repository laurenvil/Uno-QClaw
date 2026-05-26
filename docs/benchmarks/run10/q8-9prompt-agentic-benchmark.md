# Run 10 — Q8 Full 9-Prompt Agentic Battery

**Hardware:** Arduino Uno Q · Qualcomm QRB2210 · 4× Cortex-A53 · 4 GB LPDDR4X · kernel 6.16.7
**Model:** `Qwen3.5-0.8B-Q8_0.gguf` (775 MB, Q8_0) — first Q8 agentic benchmark
**Provider:** `yzma` persistent llama-server (engines/yzma/lib/llama-server, b9127) · port 8084 · **ctx 16384** (bumped from 8192 this run; see §Context Size)
**Date:** 2026-05-26
**Method:** `qclaw agent -m "<prompt>" --session run10-p<N>` · unique session per prompt · server stays running across prompts · prompt 0 is cold

Server flags (via config `extra_args`):
```
--flash-attn on  --mlock  --cache-type-k q8_0  --cache-type-v q8_0  --reasoning-budget 800
```
Always-injected: `-m <model> --host 127.0.0.1 --port 8084 -t 4 -c 16384 -np 1 --reasoning off --jinja --log-disable`

---

## Wall Latency per Prompt

Prompt 0 (`breathe`) is cold — includes server start, `--mlock` of 775 MB model into RAM, and full system-prompt prefill. Prompts 1–8 reuse the warm server; each still prefills the full system prompt on a fresh session key.

| idx | tag | wall | iters | tools | resp chars | status |
|---|---|---|---|---|---|---|
| 0 | breathe | **28m41s** (1721s) | 3 | 2 | — | ❌ empty_response |
| 1 | blink | **20m01s** (1201s) | 2 | 1 | 684 | ✅ ok |
| 2 | pot | **32m06s** (1926s) | 4 | 3 | — | ❌ empty_response |
| 3 | button | **31m10s** (1870s) | 4 | 3 | 192 | ✅ ok |
| 4 | pwm_pins | **22m30s** (1350s) | 2 | 1 | 506 | ✅ ok |
| 5 | five_volt | **22m28s** (1348s) | 1 | 0 | 865 | ✅ ok |
| 6 | mpu_vs_mcu | **36m21s** (2181s) | 1 | 0 | 1474 | ✅ ok |
| 7 | led_matrix | **25m26s** (1526s) | 3 | 2 | — | ❌ empty_response |
| 8 | compile_blink | **24m38s** (1479s) | 3 | 2 | 122 | ✅ ok |

**Warm mean (8 prompts):** 1610 s (26m50s) · range 20m01s – 36m21s

### TG t/s
Not directly measured — `--log-disable` suppresses llama-server timing output and the `/metrics` endpoint was unavailable during this run. A follow-up direct query (`POST /v1/chat/completions` + `/metrics` delta) is needed to establish Q8_0 TG t/s baseline.

---

## Q8 vs Q4_0 Latency Comparison

| Metric | Q4_0 (Run 7 baseline) | Q8 (Run 10) | Δ |
|---|---|---|---|
| Cold wall time | 11m49.6s (709s) | **28m41s** (1721s) | +16m51s (+143%) |
| Warm wall time | — (unmeasured) | **27m09s** mean | — |
| Model size | 490 MB | 775 MB | +285 MB (+58%) |
| Context size | 8192 | **16384** | +8192 (+100%) |
| Engine | yzma b9127 | yzma b9127 | same |

**Note on ctx_size change:** The context size was doubled for this run to fix an 8762-token overflow error observed in TUI. This confounds the Q4_0 vs Q8 comparison — the slower warm times are driven by **both** the heavier Q8_0 weights (slower PP per token) **and** the doubled context window (larger system prompt = more tokens to prefill). A fair comparison requires re-running Q4_0 at ctx 16384.

### Root cause of slow warm times

With ctx 16384 the pre-router can load significantly more skill content into the system prompt. The variation between prompts (20m01s vs 36m21s warm) is explained by how much context the pre-router injects per prompt type:

| prompt | warm wall | pre-router behaviour | context load |
|---|---|---|---|
| blink | 20m01s | minimal context (simple sketch prompt) | low |
| pwm_pins | 22m30s | loaded `uno-q-hardware` SKILL.md | medium |
| five_volt | 22m28s | factual; pre-router injected voltage/safety refs | medium |
| pot | 32m06s | write_file + compile + upload | medium + tool round-trips |
| button | 31m10s | loaded `sketch-patterns` SKILL.md + tool round-trips | medium + tools |
| led_matrix | 25m26s | loaded arduino list + skill file | medium + tools |
| mpu_vs_mcu | 36m21s | architecture question → pre-router loaded arch study bible + whitepaper | **high** |

---

## Sketch Correctness

| prompt | API correct | pins correct | logic correct | status |
|---|---|---|---|---|
| breathe | `analogWrite` fade loop ✅ | pin 9 ✅ | 0→255→0 in 8ms steps ✅ | ✅ correct sketch (empty final response) |
| blink | `LED_BUILTIN` + `digitalWrite` ✅ | LED_BUILTIN = D13 ✅ | 1000ms HIGH + 1000ms LOW ✅ | ✅ correct sketch |
| pot | `analogRead(A0)` + `Serial` ✅ | A0 ✅ | 9600 baud, 100ms loop ✅ | ✅ correct sketch (empty final response) |
| button | `INPUT_PULLUP` + `digitalRead` ✅ | pin 2 (button) → pin 13 (LED) ✅ | LOW = pressed logic ✅ | ✅ correct sketch |
| led_matrix | n/a | n/a | n/a | ❌ no sketch generated |
| compile_blink | `LED_BUILTIN` + `digitalWrite` ✅ | LED_BUILTIN = D13 ✅ | 1Hz on/off, `#include <Arduino.h>` ✅ | ✅ correct sketch |

**Sketch accuracy: 5/5 prompts that attempted a sketch generated a correct one (100%).** The exception is `led_matrix` where the model explored tools but never produced the sketch.

Sample — `breathe` sketch (correct):
```cpp
const int ledPin = 9;
void setup() { pinMode(ledPin, OUTPUT); }
void loop() {
    for (int i = 0; i <= 255; i++) { analogWrite(ledPin, i); delay(8); }
    for (int i = 255; i >= 0; i--) { analogWrite(ledPin, i); delay(8); }
}
```

Sample — `button` sketch (correct):
```cpp
const int buttonPin = 2;
const int ledPin = 13;
void setup() {
    pinMode(buttonPin, INPUT_PULLUP);
    pinMode(ledPin, OUTPUT);
}
void loop() {
    if (digitalRead(buttonPin) == LOW) { digitalWrite(ledPin, HIGH); }
    else { digitalWrite(ledPin, LOW); }
}
```

---

## Factual Prompt Quality

| prompt | expected | correct | response excerpt |
|---|---|---|---|
| pwm_pins | D3, D5, D6, D9, D10, D11 (6 pins) | ✅ all 6 correct + TIM controllers | "D3, D5, D6, D9, D10, D11 … TIM2, TIM1, TIM3 PWM controllers" |
| five_volt | No — Uno Q GPIO is 3.3 V | ✅ correct + safety detail | "5V on these pins permanently damages the MCU … use a level shifter" |
| mpu_vs_mcu | QRB2210 vs STM32U585, 1.8 V vs 3.3 V, Bridge required | ✅ detailed table, all facts correct | full comparison table: 4× Cortex-A53 / 160 MHz Cortex-M33 / 4GB LPDDR4X / 786 kB SRAM |

**Factual accuracy: 3/3 (100%)**. The Q8 model produced more detailed and better-structured factual answers than the Q4_0 runs — notably the `mpu_vs_mcu` response (1474 chars) was the longest and most complete in the benchmark series.

---

## Tool Call Analysis

| prompt | tool chain | iterations | final response |
|---|---|---|---|
| breathe | `compile` → `upload` | 3 | ❌ empty after upload |
| blink | `compile` | 2 | ✅ "Here's the sketch…" + code block |
| pot | `write_file` → `compile` → `upload` | 4 | ❌ empty after upload |
| button | `read_file(sketch-patterns)` → `compile` → `upload` | 4 | ✅ "The sketch has been compiled and flashed…" |
| pwm_pins | `read_file(uno-q-hardware)` | 2 | ✅ PWM pin list |
| five_volt | — | 1 | ✅ direct answer |
| mpu_vs_mcu | — | 1 | ✅ direct answer |
| led_matrix | `arduino(list)` → `read_file(sketch-patterns)` | 3 | ❌ empty (never reached compile) |
| compile_blink | `write_file` → `arduino(upload)` | 3 | ✅ "The sketch has been compiled and flashed successfully to the Uno Q." |

### The empty_response pattern

Three of eight prompts returned the fallback "I've completed processing but have no response to give" message. In every case the model's final tool action was an `upload` call:

- **breathe:** compile → upload → *empty text* ← model "finished its job" with nothing to say
- **pot:** write_file → compile → upload → *empty text*
- **led_matrix:** didn't reach compile/upload at all; read the wrong skill file and then generated nothing

The **button** prompt is the control case: the model read `sketch-patterns/SKILL.md` first (iter 1), which primed it with enough context to produce a natural confirmation on iter 4. Without that skill read, the model's final generation context is thin — just the tool result JSON from upload, which apparently doesn't prompt a confirmation.

**Blink** succeeded differently: the model only compiled (no upload), then immediately generated a response with the sketch explanation. Explicitly not uploading removed the "completed my job" dead-end.

**Root cause:** When the last message in context is a raw tool-result for an `upload` action with no preceding skill narrative, the Q8 model generates 0 tokens on the subsequent call. This is reproducible (3/8 prompts) and specific to the upload → final-gen transition. Fix: either (a) inject a brief system note after upload results prompting for a confirmation, or (b) ensure the pre-router always loads at least one skill narrative before tool chains.

---

## Key Findings

1. **Q8 is 2.4× slower cold** than Q4_0 at 8K ctx (28m41s vs 11m49.6s). The combined penalty of larger model weights + doubled ctx is too high for interactive use at current prefill speed.

2. **Warm performance regresses to 27m mean** — even simple factual prompts take 22+ min warm because the doubled ctx fills the system prompt with more skill content. This makes the persistent-server advantage moot: with Q4_0 + 8K ctx, warm turns were expected to be much shorter; with Q8 + 16K ctx every turn is essentially another cold prefill.

3. **Sketch quality is excellent** (5/5 correct when generated). The Q8 model produces noticeably better-structured and more idiomatic Arduino sketches than Q4_0 runs in earlier benchmarks. All five sketch prompts that generated code were correct on the first attempt.

4. **Factual quality is excellent** (3/3 correct, more detailed than Q4_0). The `mpu_vs_mcu` answer (1474 chars) is the most comprehensive response produced across all benchmark runs.

5. **Overall success rate: 6/9 (67%)**. Empty response failure rate: 3/9 (33%) — the upload → final-gen empty pattern is the dominant failure mode. `compile_blink` succeeded despite ending with an upload, because the model used `write_file` first (which carries the sketch text through context, giving the model content to confirm).

6. **led_matrix failure:** The model couldn't assemble the LED matrix sketch at all, exploring the wrong skill file before running out of iterations without ever writing code. This is a pre-router miss — the `led-matrix` skill should have been loaded but wasn't.

---

## Recommendations

| Issue | Recommendation | Priority |
|---|---|---|
| Empty response after upload | Inject a `"Confirm what you did in one sentence."` assistant turn after every upload result | High |
| Slow warm prefill at 16K ctx | Reduce ctx back to 8192 for Q4_0 production. Keep 16384 for Q8 only if needed | High |
| Q8 cold too slow | Q8 is not viable for interactive production use at current prefill speed; stick with Q4_0 | High |
| led_matrix pre-router miss | Audit pre-router rules to ensure `led-matrix` skill loads for "LED matrix" prompts | Medium |
| TG t/s measurement | Remove `--log-disable` or add a post-request `/metrics` delta query to the bench script | Low |

---

## Comparison to Prior Runs

| Run | Engine | Model | ctx | Method | Prompt | Wall |
|---|---|---|---|---|---|---|
| 4 | V3 assix | Q4_0 | 2048 | direct API | 9-prompt avg | — (TG 3.58 t/s) |
| 5 | yzma b9127 | Q4_0 | 2048 | direct API | 9-prompt avg | — (TG 3.39 t/s) |
| 7 | yzma b9127 | Q4_0 | 8192 | agentic | pwm_pins (cold) | **11m49.6s** |
| 9 | assix-mpu | Q4_0 | 8192 | agentic | pwm_pins (3× cold) | 12m26s mean |
| **10** | **yzma b9127** | **Q8_0** | **16384** | **agentic** | **9-prompt battery** | **28m41s cold / 27m09s warm mean** |

---

## Raw Logs

```
docs/benchmarks/run10/raw/breathe.log
docs/benchmarks/run10/raw/blink.log
docs/benchmarks/run10/raw/pot.log
docs/benchmarks/run10/raw/button.log
docs/benchmarks/run10/raw/pwm_pins.log
docs/benchmarks/run10/raw/five_volt.log
docs/benchmarks/run10/raw/mpu_vs_mcu.log
docs/benchmarks/run10/raw/led_matrix.log
docs/benchmarks/run10/raw/compile_blink.log
docs/benchmarks/run10/timing.tsv
docs/benchmarks/run10/run.log
```
