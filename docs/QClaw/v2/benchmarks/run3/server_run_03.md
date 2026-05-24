# Benchmark Results: Side-by-Side Comparison (Run 03)

**Branch:** `QClaw-GPU-CLI`
**Comparison:** Modernized Engine vs. Optimized V3 Engine
**Model:** Qwen 3.5 0.8B Q4_0
**Date:** Sunday, May 24, 2026

---

## Configuration
*   **Context Size:** 1024 tokens
*   **Threads:** 4
*   **GPU Layers:** 0 (CPU Fallback)
*   **Reasoning:** Disabled (`--reasoning off`)
*   **Prediction Length:** 128 tokens

## Performance Metrics

| Engine | Prompt Processing | Token Generation | Total Predict Time |
| :--- | :--- | :--- | :--- |
| **Modernized** | 5.89 t/s | **2.60 t/s** | 49.2s |
| **Optimized V3** | **6.08 t/s** | 2.33 t/s | 55.0s |

## Key Findings
*   **Generation Lead:** The modernized engine outperformed the V3 engine in generation speed by approximately **11.6%** (2.60 t/s vs 2.33 t/s).
*   **Prompt Parity:** The V3 engine retains a slight advantage in initial prompt processing (~3%), but this is negligible compared to the generation gains.
*   **Modernization Success:** This confirms that the surgical merge of the modern `llama.cpp` core into the Assix backend has resulted in a more efficient inference engine for the Uno Q hardware.

## Artifacts
*   **Modern Results:** `run3/modern_result.json`
*   **V3 Results:** `run3/v3_result.json`
*   **Logs:** `server_modern.log`, `server_v3.log`
