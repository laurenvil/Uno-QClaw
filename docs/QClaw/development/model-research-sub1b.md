# Sub-1B LLM Research: Alternatives to Qwen3.5-0.8B for QClaw

Research date: 2026-05-28. Goal: find small-parameter models that deliver higher token generation speed than Qwen3.5-0.8B-Q4_0 while matching or exceeding its capability on the 9-prompt QClaw agentic battery.

## Hardware Context

| Item | Value |
|---|---|
| Device | Arduino Uno Q — Qualcomm QRB2210 |
| CPU | 4× Cortex-A53 @ 2.0 GHz, ARMv8.0 |
| RAM | 4 GB LPDDR4X (~51 GB/s peak) |
| Inference | llama.cpp llama-server b9127 |
| Current model | Qwen3.5-0.8B-Q4_0 (~507 MB) |
| Current warm TG | ~5.1 t/s (bandwidth-bound) |

Token generation on Cortex-A53 is LPDDR4X bandwidth-bound: each decode step reads all model weights once. **Smaller model file = faster TG linearly.** A 470 MB model delivers ~5.5 t/s; a 305 MB model delivers ~8.3 t/s.

## QClaw Task Profile

The 9-prompt agentic battery tests three distinct capability clusters:

| Cluster | Prompts | Key requirements |
|---|---|---|
| Arduino code generation | breathe, blink, pot, button, compile_blink | Valid C++/Arduino sketch, function/tool calling for upload |
| Hardware factual recall | pwm_pins, five_volt, mpu_vs_mcu | Specific pin numbers, voltage limits, chip architecture |
| Agentic tool use | led_matrix, compile_blink, button, blink | Structured JSON tool calls, multi-step reasoning |

The factual recall cluster is the hardest to maintain when switching to smaller models — it requires hardware-specific knowledge baked into weights at training time.

---

## Top Recommendations

### 1. Qwen3-0.6B — Try First

**Summary:** Smaller sibling of Qwen3.5-0.8B in the same family. Best sub-1B tool-calling score in community benchmarks. ~7% faster TG from size alone.

| Item | Value |
|---|---|
| Parameters | 0.75B (marketed as 0.6B) |
| Q4_0 GGUF size | **470 MB** (bartowski) / 382 MB (unsloth) |
| Estimated warm TG on Uno Q | **~5.5 t/s** (+8% vs current) |
| Architecture | 28 layers, 16Q/8KV GQA, 32K context |
| License | Apache 2.0 |

**Benchmark scores:**

| Benchmark | Qwen3-0.6B | Qwen3.5-0.8B | Notes |
|---|---|---|---|
| MMLU | 52.81 | ~57 (est.) | 0.8B ~8% better knowledge recall |
| MMLU-Pro | 24.74 | 29.7 | 0.8B ~20% better — risk for factual prompts |
| MBPP (base) | 36.60 | N/A reported | Adequate for sketch generation |
| Tool-calling (agent score) | **0.880** (#3/21 models) | 0.640–0.880 range | Beats phi4-mini 3.8B (0.780) |
| Tool restraint (no false calls) | 1.000 (perfect) | N/A | Critical for QClaw agent loop |

**llama.cpp compatibility:** Natively supported. `--jinja` flag (already pinned by QClaw provider) handles the Qwen3 chat template. `--reasoning off` + `--reasoning-budget 800` work identically. Jinja template bugs fixed August 2025.

**Risk:** MMLU-Pro gap (~20%) means pwm_pins, five_volt, and mpu_vs_mcu prompts may regress. These rely on hardware-specific knowledge that is more abundant in the 0.8B's larger weight budget. **Verdict: run the 9-prompt battery before adopting.**

**Config change:** update `model` field only — no other changes needed.

```jsonc
"model": "llama-server/Qwen3-0.6B-Q4_0.gguf"
```

**Download:**
- Official: https://huggingface.co/Qwen/Qwen3-0.6B-GGUF
- bartowski (Q4_0 = 470 MB): https://huggingface.co/bartowski/Qwen_Qwen3-0.6B-GGUF
- unsloth (Q4_0 = 382 MB): https://huggingface.co/unsloth/Qwen3-0.6B-GGUF

---

### 2. Qwen2.5-Coder-0.5B — Speed-Only Trade

**Summary:** Coding-specialized, ~305 MB, estimated ~8.3 t/s (+63% vs current). Likely passes code-generation prompts but risks failing factual recall and mpu_vs_mcu.

| Item | Value |
|---|---|
| Parameters | 0.5B |
| Q4_0 GGUF size | ~305 MB |
| Estimated warm TG on Uno Q | **~8.3 t/s** (+63% vs current) |
| HumanEval | 28.0% |
| MBPP | 52.9% |
| Tool-calling agent score | 0.640 |
| llama.cpp tool-call support | Native (explicitly listed) |

**Verdict:** Only viable if the pre-router system prompt can compensate for weaker factual recall (inject pin tables, voltage rules directly). Not recommended as a drop-in without extensive testing.

**Download:** https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF

---

## Full Candidate Table

| Model | Params | Q4_0 Size | Est. TG | HumanEval | IFEval | Tool-call (agent) | llama.cpp native | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Qwen3.5-0.8B** ⭐ | 0.9B | 507 MB | 5.1 t/s | — | 59.94 | 35.08 BFCLv3 | ✅ | Current baseline |
| **Qwen3-0.6B** | 0.75B | 470 MB | ~5.5 t/s | ~36 est. | ~52 est. | 0.880 | ✅ | **Try first** |
| Qwen2.5-Coder-0.5B | 0.5B | ~305 MB | ~8.3 t/s | 28.0 | — | 0.640 | ✅ | Speed-only trade |
| Qwen2.5-Coder-1.5B | 1.5B | 1.07 GB | ~2.4 t/s | 43.9 | — | — | ✅ | Over budget, too slow |
| LFM2.5-1.2B-Instruct | 1.2B | 696 MB | ~3.7 t/s | — | 86.23 | 49.12 BFCLv3 | ❌ custom format | Not for coding; incompatible tool format |
| LFM2.5-350M | 0.35B | ~215 MB | ~12 t/s | — | 76.96 | 44.11 BFCLv3 | ❌ custom format | Incompatible tool format; not for code |
| Gemma 3 1B | 1.0B | 720 MB | ~3.6 t/s | 41.5 | 63.49 | 16.61 BFCLv3 | ❌ no tool tokens | No native tool calling; over budget |
| Llama 3.2 1B | 1.0B | ~720 MB | ~3.6 t/s | — | — | 25.7 BFCLv2 | ✅ | Weak tool use; over budget |
| SmolLM2-360M | 0.36B | ~220 MB | ~11 t/s | — | 41.0 | 0.640 | ❌ | Too weak for factual recall |
| SmolLM2-1.7B | 1.7B | ~1.1 GB | ~2.4 t/s | 22.6 | — | 0.640 | ❌ | Over budget; poor coding score |
| Granite 4.0 Nano 350M | 0.35B | ~215 MB | ~12 t/s | — | 53.48 | 39.58 BFCLv3 | ❌ | Insufficient data; no llama.cpp native |
| MobileLLM-350M/1B | 0.35–1B | ~220–610 MB | varies | — | — | — | ❌ | Research model; no llama.cpp GGUF path |
| SmolLM3-3B | 3.0B | ~1.9 GB | ~1.4 t/s | — | — | — | ❌ | Way over budget |
| Phi-4 Mini | 3.8B | ~2.4 GB | ~1.1 t/s | strong | — | 0.780 | ❌ | Way over budget |
| Gemma 3n E2B | 6B raw / ~2B eff. | unclear | unclear | — | — | — | ❌ | Effective footprint unclear on CPU |

TG estimates use: `TG ≈ (calibrated bandwidth) / model_size_MB × 507 × 5.1` based on observed Qwen3.5-0.8B result.

---

## Key Finding: Is Qwen3.5-0.8B Near-Optimal?

**Yes, for this size class and task profile — but Qwen3-0.6B is worth one benchmark run.**

The 2025 sub-1B landscape forms a Pareto frontier almost entirely from the Qwen family:

```
TG (t/s)   Capability
  12 ─── SmolLM2-360M         │ too weak for factual recall
   8 ─── Qwen2.5-Coder-0.5B  │ misses factual prompts
 5.5 ─── Qwen3-0.6B          │ ← best trade-off candidate
 5.1 ─── Qwen3.5-0.8B ⭐    │ current champion on knowledge benchmarks
 3.7 ─── LFM2.5-1.2B         │ not for coding; incompatible tool format
 3.6 ─── Gemma 3 1B           │ no tool calling
 2.4 ─── Qwen2.5-Coder-1.5B  │ best coding but over budget
```

The LFM2 hybrid (SSM+Transformer) architecture delivers impressive IFEval and BFCLv3 scores at 1.2B but is blocked by:
1. Custom Pythonic tool-call format — not OpenAI-compatible JSON
2. Explicitly not recommended for coding by its own model card
3. Heavier than the current model and slower TG

**Architectural reason Qwen dominates:** Alibaba trained the Qwen3 series on a very large, high-quality corpus at every size from 0.6B up, giving sub-1B models knowledge density well above their parameter count. No other lab has matched this at 0.6–0.8B as of mid-2026.

---

## Recommended Benchmark Run

To validate Qwen3-0.6B before adoption, run the existing bench script against this model:

```bash
# Download
wget -O ~/models/Qwen3-0.6B-Q4_0.gguf \
  'https://huggingface.co/bartowski/Qwen_Qwen3-0.6B-GGUF/resolve/main/Qwen_Qwen3-0.6B-Q4_0.gguf'

# Add a model_list entry for yzma-q3-0.6b (port 8086) in ~/.qclaw/config.json
# then run the 9-prompt battery:
bash scripts/bench-run18-yzma-q3-0.6b.sh
```

The three prompts to watch closely: **pwm_pins**, **five_volt**, **mpu_vs_mcu**. If all three pass, Qwen3-0.6B is a drop-in upgrade. If any fail, they can likely be salvaged by injecting the relevant skill content more aggressively via the pre-router (the system prompt already does this for pwm_pins and five_volt via `uno-q-hardware` skill).

---

## Sources

- Qwen3 Technical Report — arXiv 2505.09388
- Qwen3-0.6B model card — huggingface.co/Qwen/Qwen3-0.6B
- Qwen3.5-0.8B vs Qwen3-0.6B community discussion — huggingface.co/Qwen/Qwen3.5-0.8B/discussions/6
- Tool-calling benchmark (lintware fork, CPU, 21 models) — github.com/lintware/tool-calling-benchmark
- LFM2.5-1.2B-Instruct model card — huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct
- LFM2.5-350M benchmark blog — liquid.ai/blog/lfm2-5-350m-no-size-left-behind
- Gemma 3 Technical Report — arXiv 2503.19786
- SmolLM2 paper — arXiv 2502.02737
- Qwen2.5-Coder Technical Report — arXiv 2409.12186
- llama.cpp function calling docs — github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md
- IBM Granite 4.0 Nano — VentureBeat, Oct 2025
- Cloud-to-Edge LLM benchmarking on single-board computers — arXiv 2604.24785
- On-Device Qwen2.5 with compression on Cortex-A53 — arXiv 2504.17376
