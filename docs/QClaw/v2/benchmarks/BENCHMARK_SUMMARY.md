# QClaw llama-server Benchmark Summary

**Hardware:** Arduino Uno Q · Qualcomm QRB2210 · 4× Cortex-A53 · 4 GB LPDDR4X · kernel 6.16.7
**Model:** `Qwen_Qwen3.5-0.8B-Q4_0.gguf` (490 MB, Q4_0)
**Runs:** 1–9 · **All CPU-only** (GPU dropped at init, see §GPU Status)

---

## The Three Engines

| Engine | Branch | Source repo | Commit | Binary on device | Size |
|---|---|---|---|---|---|
| **Main (Yazma)** | `main` | hybridgroup/yzma · main | a9883db8 (b9127) | `ArduinoApps/yzma/lib/llama-server` | 9.0 MB |
| **Optimized V3** | `qclaw-llmaCLI-v3` | assix/Arduino-UnoQ-Optimized-Llama-CLI · mpu | aca9a0f | `qclaw/engines/llamacli/mpu/llama-server` ⭐ | 16 MB |
| **Modernized (Surgical)** | `QClaw-GPU-CLI` | laurenvil/Uno-QClaw (in-tree llama.cpp) | 832d383 | `qclaw/llama.cpp/build/bin/llama-server` | 9.8 MB |

⭐ = currently active binary in QClaw-v2 (`~/.qclaw/config.json`)

**Why V3 is 16 MB:** statically links libllama, libggml, and OpenCL backend into one binary. The other two link shared `.so` files at runtime, keeping the executable small.

---

## Per-Run Results

### Runs 1–2 — c512, n64, cold/hot

| Run | Engine | PP (t/s) | TG (t/s) | Wall | Notes |
|---|---|---|---|---|---|
| 1 | Modernized | 5.51 | 3.61 | 18.8 s | First measurement of surgical build |
| 2 cold | V3 assix | 5.59 | 3.59 | — | Essentially identical to Run 1 |
| 2 hot | V3 assix | 5.38 | 3.13 | — | No KV cache benefit at 6-token prompt |

### Run 3 — c1024, n128, side-by-side

| Engine | PP (t/s) | TG (t/s) | Total predict |
|---|---|---|---|
| Modernized (Surgical) | 5.89 | **2.60** | 49.2 s |
| V3 assix | **6.08** | 2.33 | 55.0 s |

Modernized wins generation by +11.6%; V3 leads prompt processing by ~3%.

### Run 4 — c2048, n128, full 9-prompt battery

| Prompt | Modernized | V3 |
|---|---|---|
| breathe | **3.59** | 3.18 |
| blink | **3.61** | 3.32 |
| pot | 3.00 | **3.02** |
| button | **3.27** | 3.21 |
| pwm_pins | **3.45** | 3.42 |
| five_volt | 3.43 | **3.59** |
| mpu_vs_mcu | **3.51** | 3.37 |
| led_matrix | **3.55** | 3.51 |
| compile_blink | **3.68** | 3.58 |
| **Average** | **3.45** | **3.36** |

Modernized leads by ~2.7% on the full battery.

### Run 5 — c2048, n128, 3-way including Yazma

| Prompt | Main (Yazma) | V3 assix | Modernized |
|---|---|---|---|
| breathe | 3.16 | **3.54** | 2.84 |
| blink | **3.83** | 3.47 | 2.60 |
| pot | 3.10 | **3.48** | 2.56 |
| button | 3.25 | **3.41** | 2.61 |
| pwm_pins | 2.96 | **3.48** | 2.68 |
| five_volt | **3.86** | 3.21 | 2.39 |
| mpu_vs_mcu | 3.40 | **3.87** | 2.66 |
| led_matrix | 3.57 | 3.04 | 2.63 |
| compile_blink | 3.41 | **3.48** | 2.61 |
| **Average** | **3.39** | **3.44** | **2.62** |

V3 assix edges Yazma by 1.5%. Modernized regresses vs. Run 4 — the in-tree ggml build carries more runtime overhead than the pre-compiled assix MPU binary on short-context tasks.

### Today's partial session (3/9 prompts, shared session key)

Same binary as V3 (assix mpu/llama-server aca9a0f) via QClaw-v2 persistent server. Context accumulated across turns in a single `cli:direct` session, degrading KV attention cost each turn:

| Prompt | TG (t/s) | Wall |
|---|---|---|
| breathe | 2.36 | 18m12s |
| blink | 2.44 | 13m15s |
| pot | 2.91 | 18m33s |

Aborted. Root cause: shared session key (`cli:direct`) across all 9 prompts forces full transcript re-prefill each turn. Use `--session` with a unique key per prompt for controlled benchmarks.

---

## llama-cli (one-shot subprocess) Reference Numbers

From the `QClaw-Client` / `qclaw-llmaCLI-v2` branch benchmark — binary: `engines/llamacli/mpu/llama-cli` (same assix aca9a0f build, llama.cpp `b9099-5d5d2e15d`), warm cache:

| n tokens | PP (t/s) | TG (t/s) | Wall |
|---|---|---|---|
| n=16 | 10.5 | 8.9 | 10.39 s |
| n=64 | **10.6** | **8.8** | 10.34 s |
| n=128 | 10.7 | 4.8 | 16.31 s |
| cold start | 5.7 | — | 12.17 s |

These numbers are higher than the llama-server equivalents because llama-cli has no HTTP boundary, no chat-template parser, and no parallel slot overhead. The 10.6 t/s PP and 8.8 t/s TG are the hardware ceiling for this model on CPU at short sequence lengths.

Yzma b9127 baseline (same model, prior HTTP server): PP 5.37 t/s · TG 3.69 t/s · wall 20.90 s — assix mpu is ~2× faster end-to-end.

---

## GPU Status

Every binary drops the Adreno 702 at init. Two compounding causes:

1. **Device-name gate** — Mesa rusticl reports the GPU as `FD702` (Freedreno), not `Adreno`/`Qualcomm`. ggml's OpenCL backend allowlist rejects it before loading any kernel.
2. **Missing subgroup extension** — rusticl 25.2.6 does not expose `cl_khr_subgroups`, required unconditionally by ggml's softmax and RMS-norm OpenCL kernels.

The Vulkan path (`llama-opencl/build-vulkan/bin/llama-server`, 75 MB, ggml-org d4b0c22) did engage the Adreno 702 via Turnip but yielded **0.46 t/s PP / 0.25 t/s TG** — unusable.

---

## Full Device Inventory

| # | Binary | Project | Backends | TG (t/s) | Status |
|---|---|---|---|---|---|
| 1 | `yzma/lib/llama-server` | hybridgroup/yzma b9127 | RPC + CPU armv8 | 3.39 avg | Measured (Run 5) |
| 2 | `qclaw/engines/llamacli/mpu/llama-server` ⭐ | assix aca9a0f | OpenCL→CPU | 3.44 avg | Measured (Runs 2–5) |
| 3 | `qclaw/llama.cpp/build/bin/llama-server` | Uno-QClaw in-tree | OpenCL→CPU | 2.62 avg | Measured (Runs 1, 3–5) |
| 4 | `qclaw/engines/llamacli/llama.cpp/build/bin/llama-server` | assix aca9a0f (alt build) | OpenCL→CPU | — | Not benchmarked separately |
| 5 | `llama-vulkan-lib/llama-b9049/llama-server` | ggml-org b9049 | Vulkan | — | Not benchmarked |
| 6 | `llama-vulkan-v2/build-vulkan/bin/llama-server` | ggml-org 2496f9c | Vulkan | — | Not benchmarked |
| 7 | `llama-opencl/build-vulkan/bin/llama-server` | ggml-org d4b0c22 | OpenCL (Vulkan path) | 0.25 | Measured (V2 GPU run) |
| 8 | `llama-wang/build/bin/llama-server` | wanghqc/llama.cpp opencl/nvidia | OpenCL Adreno-specific | — | **Not benchmarked — highest priority** |
| 9 | `yzma/lib/_backup_.../llama-server` | yzma pre-b9127 backup | CPU only | — | Archived |
| 10 | `yzma/lib/_backup_.../llama-b9014/llama-server` | yzma b9014 | Vulkan + CPU | — | Archived |
| 11 | `Sensai/yzma/lib-vulkan/llama-server` | ggml-org 2496f9c | Vulkan | — | Not benchmarked |
| 12 | `Sensai/vulkan-build-source/build-vulkan/bin/llama-server` | ggml-org 2496f9c | Vulkan | — | Not benchmarked |

---

## Headline Numbers

| Engine | Best TG (t/s) | Best PP (t/s) | GPU |
|---|---|---|---|
| Main / Yazma b9127 | 3.86 | 5.37 | ✗ CPU only |
| **V3 assix mpu aca9a0f** ⭐ | **3.87** | **10.6** (llama-cli) | ✗ OpenCL drops |
| Modernized Surgical | 3.68 | 5.89 | ✗ OpenCL crashes at decode (`GGML_ASSERT(0)` in compat path) |
| Adreno-tuned assix (fresh build, Run 6) | n/a | n/a | ✗ OpenCL kernel compile fails (`sub_group_reduce_add` not declared on rusticl) |
| Vulkan llama-opencl d4b0c22 | 0.25 | 0.46 | ✓ active but unusable |
| llama-wang opencl/nvidia | — | — | ? remains untested |

**Run 6 finding (2026-05-24):** The structural blocker on this hardware is rusticl's missing `cl_khr_subgroups`. Both modernized engines (Surgical and Adreno-tuned assix) get past the device-name allowlist and the subgroup-extension check, but the kernel source code itself uses `get_sub_group_id` and `sub_group_reduce_add` as direct OpenCL C builtins that rusticl cannot resolve. See [run6/three-engine-comparison.md](run6/three-engine-comparison.md) for full details.

### Run 7 — Yzma integration + study-bible optimization pass (2026-05-25)

Yzma added as QClaw-v2's fourth engine via `.gitmodules` submodule + `model_list` config entry
(port 8083, lib_path `/home/arduino/ArduinoApps/yzma/lib`). New provider features: `WithParallel`
option (default 1, fixes auto-slot ctx overflow on b9127+) and `extra_args` passthrough from
`extra_body` (generic mechanism for per-engine server flags, no Go changes needed for new flags).

| Config | Wall (cold) | Response | Notes |
|---|---|---|---|
| Baseline (`-np 1` only) | **11m49.6s** | 241 chars ✅ | Fastest engine to date |
| Optimized (flash-attn, mlock, q8_0 KV, reasoning-budget 800) | 12m43.2s | 146 chars ✅ | 53s regression on cold |

**Key finding:** Yzma baseline cold (11m49.6s) beats assix-mpu cold (17m54s, Run 6) by **6m04s**
on the same prompt and model, both CPU-only. The `--mlock` + `--flash-attn` flags add upfront cost
on a cold run; warm-path benefit remains unmeasured.

### Run 8 — Four-engine optimized comparison (2026-05-25)

Applied the same five-flag optimization set (`--flash-attn on`, `--mlock`, `--cache-type-k/v q8_0`,
`--reasoning-budget 800`) to assix-mpu, surgical, and yzma via the `extra_args` passthrough.
assix-adreno binary doesn't support these flags.

| Engine | Wall | Exit | vs unoptimized |
|---|---|---|---|
| **assix-mpu optimized** ⭐ | **12m35.1s** | 0 ✅ | −5m19s vs Run 6 (−30%) |
| yzma optimized | 12m58.1s | 0 ✅ | +1m09s vs Run 7 baseline (+10%) |
| surgical optimized | 36s | 1 ❌ | OpenCL crash (same as Run 6) |
| assix-adreno | 5m00s (timeout) | 124 ⏱ | OpenCL kernel compile hang |

**Headline finding:** The flag set inverts the engine ranking. Yzma was fastest pre-optimization
(11m49.6s, Run 7). After optimization, **assix-mpu wins** (12m35.1s) by 23 seconds. The older
assix llama.cpp benefits dramatically from flash-attn + mlock; yzma's newer build (b9127) appears
to have those gains baked in already, so the flags only add cost.

Full report: [run8/four-engine-optimized-comparison.md](run8/four-engine-optimized-comparison.md).

### Run 9 — Three-engine, three-sample comparison + llama-cli probe (2026-05-25)

Re-ran pwm_pins 3× each on assix-mpu and yzma (both optimized) to validate Run 8's inversion.
Also added a `llamacli-mpu` model entry to probe llama-cli as a direct-path alternative.

| Engine | Mean wall (3 runs) | σ | Verdict |
|---|---|---|---|
| **assix-mpu optimized** ⭐ | **12m26s** (746s) | 2s | Tight, reproducible, fastest |
| yzma optimized | 12m35s (755s) | 4s | Tight, 8s slower than assix-mpu |
| llamacli-mpu (yzma binary) | 1200s killed | — | **Repetition loop** — model loops forever, qclaw timeout fires |

Run 8's 23s assix→yzma gap shrinks to 8s with three samples (was half signal, half noise). The
directional finding holds: assix-mpu optimized is the fastest viable engine on this hardware.

**Llama-cli direct-path probe:** The assix `engines/llamacli/mpu/llama-cli` binary is now broken
on this hardware (same OpenCL kernel compile failure as assix-adreno). Repointed at yzma's CPU+RPC
llama-cli — that binary runs, but the llamacli provider has no repetition controls, and the 0.8B
Qwen model deterministically falls into the loop documented in main's whitepaper §9.2. Verdict:
**llama-cli is not viable for the direct path until the llamacli provider adds `--repeat-penalty`
and a no-progress wall-clock guard.** Until then, yzma llama-server is the direct-path default.

Full report: [run9/three-engine-3x-comparison.md](run9/three-engine-3x-comparison.md).

### Run 10 — Q8 full 9-prompt agentic battery (2026-05-26)

First benchmark with `Qwen3.5-0.8B-Q8_0.gguf` (775 MB, Q8_0) across all 9 standard prompts.
Context size bumped 8192 → 16384 this run (8762-token overflow fix). Unique session per prompt,
server stays warm between prompts.

| Metric | Value |
|---|---|
| Cold wall (breathe, prompt 0) | **28m41s** (vs Q4_0 11m49.6s, +143%) |
| Warm mean (prompts 1–8) | **26m39s** (range 20m01s – 36m21s) |
| Success rate | **8/9 ✅** · 1/9 empty_response ❌ (breathe only; pot + led_matrix rerun ✅) |
| Sketch correctness | **6/6 correct** (all sketch prompts, including reruns) |
| Factual accuracy | **3/3 correct**, more detailed than Q4_0 |

**Headline finding:** Q8 + 16K ctx is 2–3× slower than Q4_0 + 8K ctx on every metric. The
doubled context window loads more skill content per prompt, making warm turns as slow as cold
runs. Q8 is not viable for interactive production use at current prefill speed; retain Q4_0 for
production and reserve Q8 for offline/batch use cases.

**empty_response pattern is probabilistic:** Original run had 3/9 empty_response failures.
Reruns of pot and led_matrix both succeeded with fresh session keys (temperature=0.3 variance).
Only `breathe` remains unconfirmed. A post-upload confirmation prompt injection would reduce
variance further.

Full report: [run10/q8-9prompt-agentic-benchmark.md](run10/q8-9prompt-agentic-benchmark.md).

### Run 11 — Q8 + `--reasoning off` + `/no_think` (2026-05-27, partial 7/9)

Same model and ctx as Run 10. Added `--reasoning off` to `extra_args` and `/no_think` as first
line of `SOUL.md`. Run cancelled after prompt 6; led_matrix and compile_blink not executed.

| Metric | Value |
|---|---|
| Cold wall (breathe, prompt 0) | **25m55s** (vs 28m41s Run 10, −10%) |
| Warm mean (prompts 1–6, partial) | **24m12s** (vs 26m39s Run 10, −9.2%) |
| Success rate | **7/7 ✅** (0 empty_response) |
| empty_response pattern | **Eliminated** — breathe (compile→upload) passed cleanly |

**Headline finding:** `--reasoning off` + `/no_think` fixes the upload → empty failure mode and
cuts warm latency ~9% across the board. Recommended as the new standard config for yzma-q8.

Full report: [run11/q8-reasoning-off-benchmark.md](run11/q8-reasoning-off-benchmark.md).

### Run 14 — Q4_0 Final 9-Prompt Agentic Battery + TG/PP Probe (2026-05-27)

Default yzma model (`Qwen_Qwen3.5-0.8B-Q4_0.gguf`, 490 MB, Q4_0) with study-bible flags and
`--reasoning-budget 800`. First run to capture real TG/PP t/s via direct `/v1/chat/completions`
timing probe after each agentic call. Run interrupted at prompt 6 by session compaction; resumed
from warm server — all 9 results valid.

| Metric | Value |
|---|---|
| Cold wall (breathe, prompt 0) | **30m48s** (1848s) |
| Warm mean (prompts 1–8) | **25m30s** (1531s, range 18m58s – 35m55s) |
| Total inference time | **3h54m55s** (14095s) |
| Success rate | **8/9 ✅** · 1/9 empty_response (led_matrix, post-upload) |
| Sketch correctness | **5/5 correct** (breathe, blink, pot, led_matrix, compile_blink) |
| PP cold | 8.54 t/s |
| PP warm avg | **11.20 t/s** |
| TG cold | 2.26 t/s |
| TG warm avg | **5.07 t/s** |
| TG warm/cold speedup | **2.24×** |

**TG is memory-bandwidth-bound on LPDDR4X:** warm ceiling is ~5.1–5.2 t/s across all prompt
types; no flag tuning will push past this on Cortex-A53. PP ceiling is ~11.4 t/s warm. Cold TG
depressed (2.26 t/s) by 16K-token prefill filling LPDDR4X bandwidth during initial KV cache load.

**`--reasoning-budget 800` vs `--reasoning off`:** Cold time (30m48s) is longer than Run 10 Q8
cold (28m41s) despite Q4_0 being smaller — extra thinking tokens inflate the cold prefill.
1/9 empty_response persists. For production use, `--reasoning off --reasoning-budget 0`
(Run 11 finding) is preferred: eliminates empty_response and reduces warm mean by ~5%.

**ctx 16384 confirmed correct:** sufficient for full skill injection without overflow.
ctx 8192 overflows at iter 3 on tool-heavy prompts (Run 13).

Full report: [run14/q4-final-benchmark.md](run14/q4-final-benchmark.md).

### Run 15 — Q4_0 yzma ctx 9000 + repeat-penalty flags (2026-05-29, aborted)

First run with `ctx_size 9000` (down from 16384) and new `--repeat-penalty 1.1 --repeat-last-n 64` flags on the yzma b9127 engine. Aborted after prompt 2 due to KV cache collapse.

| Metric | Value |
|---|---|
| Prompts attempted | 3 / 9 (aborted) |
| Prompts ok | 2 / 3 (breathe, blink) |
| Status at abort | pot: empty_response + TG collapse; button/pwm_pins: error(1) wall=0s |
| Cold wall (breathe) | 25m42s |
| Warm wall (blink) | 17m56s |
| TG at breathe/blink | 5.13 / 5.15 t/s (normal) |
| TG at pot probe | **0.92 t/s** (collapsed from 5.15) |

**Root cause:** ctx 9000 is too small for yzma b9127 on multi-tool sessions. The pot prompt accumulated enough session history + tool call context to saturate the 9,216-token KV budget. Once saturated, TG dropped to 0.92 t/s and all subsequent prompts exited immediately (server in degraded state). yzma's newer llama.cpp base (b9127) appears to handle cumulative session KV differently than older builds — ctx 9000 worked correctly for llamacli-mpu (older base, Run 17) but not for yzma.

### Run 16 — llama-wang engine (2026-05-29, crashed prompt 0)

First test of `/home/arduino/ArduinoApps/llama-wang/build/bin/llama-server` — the Adreno-targeted OpenCL fork. Crashed after 37s on prompt 0.

| Metric | Value |
|---|---|
| Prompts attempted | 1 / 9 |
| Crash type | `GGML_ASSERT(0)` at OpenCL kernel compilation |
| Wall time before crash | 37s |

**Root cause:** Mesa rusticl on the FD702 drops `cl_khr_subgroups`, causing llama.cpp to fall back to the Q4_0 **noshuffle** kernel path. llama-wang is missing all three noshuffle kernels: `gemv_noshuffle_q4_0_f32.cl`, `gemv_noshuffle_q4_0_f32_spec.cl`, `gemm_noshuffle_q4_0_f32.cl`. The `QClaw-GPU-CLI` branch of `assix/Arduino-UnoQ-Optimized-Llama-CLI` adds these kernels — that build became Run 17's engine.

### Run 17 — llamacli-mpu (e6ed0a2, GPU-CLI) ctx 9000 · full 9-prompt battery (2026-05-29)

First successful full battery with the GPU-CLI static binary at ctx 9000. OpenCL init fails (rusticl missing `sub_group_reduce_add`) → CPU fallback. TG matches yzma's LPDDR4X ceiling.

| Metric | Value |
|---|---|
| Engine | `engines/llamacli/mpu/llama-server` (e6ed0a2, static 16 MB) |
| Prompts ok | **7 / 9** |
| empty_response | 1 / 9 (led_matrix) |
| error(1) | 1 / 9 (mpu_vs_mcu — ctx overflow: 10,345 tok > 9,216 budget) |
| Cold wall (breathe) | **26m52s** (−3m56s vs Run 14) |
| Warm mean wall | **23m27s** (−2m03s vs Run 14) |
| PP warm avg | **11.40 t/s** |
| TG warm avg | **5.09 t/s** |

**Headline findings:**
- llamacli-mpu handles ctx 9000 stably across 8 consecutive warm prompts — no KV collapse
- Warm wall time is ~8% faster than Run 14 (yzma ctx 16384) purely from smaller prefill cost
- TG ceiling unchanged at ~5.1 t/s — both engines are LPDDR4X bandwidth-bound on Cortex-A53
- mpu_vs_mcu overflow is deterministic: that prompt's skill injection totals 10,345 tokens; requires `ctx_size ≥ 11,000`
- led_matrix empty_response is probabilistic (same pattern as Run 14)
- Default config reverted to yzma (port 8083) with all run-17 flags; llamacli-mpu retained as `engines/llamacli/mpu/llama-server` for reference

Full report: [run17/run17-llamacli-mpu-benchmark.md](run17/run17-llamacli-mpu-benchmark.md).

---

**Next steps (in priority order):**
1. Run 18: benchmark Qwen3-0.6B-Q4_0 on yzma — validate 9-prompt battery pass rate before adopting as default model (see `docs/QClaw/development/model-research-sub1b.md`)
2. Fix mpu_vs_mcu ctx overflow: raise `ctx_size` to 11000 in the default yzma entry and re-run that single prompt
3. Warm-direct benchmark on yzma — measure KV prefix-cache hit rate to settle whether persistent server actually helps repeated direct queries
4. Patch Adreno kernels to use workgroup-level reductions instead of subgroup reductions (large diff)
5. Track Mesa rusticl `cl_khr_subgroups` implementation
