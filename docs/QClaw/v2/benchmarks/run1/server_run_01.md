# Benchmark Results: llama-server (Run 01)

**Branch:** `QClaw-GPU-CLI`
**Engine:** Modernized `llama-server` (Surgical Merge with Assix Backend)
**Model:** Qwen 3.5 0.8B Q4_0 (`Qwen_Qwen3.5-0.8B-Q4_0.gguf`)
**Date:** Saturday, May 23, 2026

---

## Hardware Environment
*   **Platform:** Arduino Uno Q
*   **CPU:** 4 Cores
*   **GPU:** Adreno 702 / FD702 (OpenCL 3.0)
*   **Memory:** 3.6Gi Total / ~2.6Gi Available

## Configuration
*   **Context Size:** 512 tokens
*   **Threads:** 4
*   **GPU Layers:** 0 (CPU Fallback confirmed)
*   **Reasoning:** Disabled (`--reasoning off`)

## Performance Metrics

| Metric | Result | Notes |
| :--- | :--- | :--- |
| **Prompt Processing** | **5.51 t/s** | Evaluated 6 tokens in 1.09s |
| **Token Generation** | **3.61 t/s** | Generated 64 tokens in 17.75s |
| **Total Response Time** | **18.8s** | Including initialization and overhead |

## Comparative Analysis
*   **vs. `v3` Branch:** `v3` reported ~7.5 t/s prompt and ~6.1 t/s decode. Our current build matches the prompt processing speed (~7.5 t/s in CLI) but shows a regression in generation speed (3.6 t/s vs 6.1 t/s).
*   **Reason for regression:** This build uses the modern `llama.cpp` core which may have higher overhead for small models, or lacks the specific Assix math library optimizations that were present in the pre-compiled binaries.

## Artifacts
*   **Server Log:** `server_no_reasoning.log` (Internal)
*   **Benchmark Command:** `curl -X POST http://localhost:8080/completion -d '{"prompt": "...", "n_predict": 64}'`
