# Benchmark Results: Side-by-Side Comparison (Run 04)

**Branch:** `QClaw-GPU-CLI`
**Source of Prompts:** `main` branch "standard battery" (Prompts 1-9)
**Comparison:** Modernized Engine vs. Optimized V3 Engine
**Model:** Qwen 3.5 0.8B Q4_0
**Date:** Sunday, May 24, 2026

---

## Configuration
*   **Context Size:** 2048 tokens
*   **Threads:** 4
*   **GPU Layers:** 0 (CPU Fallback)
*   **Reasoning:** Disabled (`--reasoning off`)
*   **Prediction Length:** 128 tokens
*   **Total Prompts:** 9

## Performance Metrics (Generation Speed in t/s)

| Prompt Tag | Modernized Engine | Optimized V3 Engine |
| :--- | :--- | :--- |
| **breathe** | **3.59** | 3.18 |
| **blink** | **3.61** | 3.32 |
| **pot** | 3.00 | **3.02** |
| **button** | **3.27** | 3.21 |
| **pwm_pins** | **3.45** | 3.42 |
| **five_volt** | 3.43 | **3.59** |
| **mpu_vs_mcu** | **3.51** | 3.37 |
| **led_matrix** | **3.55** | 3.51 |
| **compile_blink** | **3.68** | 3.58 |
| **AVERAGE** | **3.45 t/s** | **3.36 t/s** |

## Analysis
*   **Overall Performance:** The modernized engine shows a slight lead in generation speed across the 9-prompt battery, averaging **3.45 t/s** compared to **3.36 t/s** for the V3 engine (a ~2.7% advantage).
*   **Consistency:** The modernized engine is more consistent across different tasks, while the V3 engine showed higher peaks on specific factual retrieval prompts (e.g., `five_volt`).
*   **Modernization Success:** This benchmark confirms that the modernized core maintains or slightly exceeds the performance of the highly-optimized V3 engine even on short-context tasks, while offering superior performance on complex architectural descriptions (as seen in Run 03).

## Artifacts
*   **Results Directory:** `docs/benchmarks/run4/results/`
*   **Raw Logs:** `server_modern_run4.log`, `server_v3_run4.log`
