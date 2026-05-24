# QClaw llama-server Benchmark Summary

**Hardware:** Arduino Uno Q · Qualcomm QRB2210 · 4× Cortex-A53 · 4 GB LPDDR4X · kernel 6.16.7
**Model:** `Qwen_Qwen3.5-0.8B-Q4_0.gguf` (490 MB, Q4_0)
**Runs:** 1–5 + today's partial session · **All CPU-only** (GPU dropped at init, see §GPU Status)

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
| Modernized Surgical | 3.68 | 5.89 | ✗ OpenCL drops |
| Vulkan llama-opencl d4b0c22 | 0.25 | 0.46 | ✓ active but unusable |
| llama-wang opencl/nvidia | — | — | ? highest-priority next test |

**Next step:** benchmark `llama-wang/build/bin/llama-bench` — the only Adreno-targeted OpenCL fork (`wanghqc/llama.cpp · opencl/nvidia`, commit 8c5aa97, April 2026 Q4_K GEMV fix) that has not been tested on this hardware.
