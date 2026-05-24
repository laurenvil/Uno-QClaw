# Benchmark Results: 3-Way Engine Comparison (Run 05)

**Branch:** `QClaw-v2`
**Comparison:** Main (Yazma) vs. Optimized V3 vs. Modernized (Surgical)
**Model:** Qwen 3.5 0.8B Q4_0
**Date:** Sunday, May 24, 2026

---

## Configuration
*   **Context Size:** 2048 tokens
*   **Threads:** 4
*   **GPU Layers:** 0 (CPU Fallback for all)
*   **Reasoning:** Disabled (`--reasoning off`)
*   **Prediction Length:** 128 tokens
*   **Battery:** 9 standard prompts from `main`

## Performance Metrics (Generation Speed in t/s)

| Prompt Tag | Main (Yazma) | Optimized V3 | Modernized (Surgical) |
| :--- | :--- | :--- | :--- |
| **breathe** | 3.16 | **3.54** | 2.84 |
| **blink** | **3.83** | 3.47 | 2.60 |
| **pot** | 3.10 | **3.48** | 2.56 |
| **button** | 3.25 | **3.41** | 2.61 |
| **pwm_pins** | 2.96 | **3.48** | 2.68 |
| **five_volt** | 3.86 | 3.21 | 2.39 |
| **mpu_vs_mcu** | 3.40 | **3.87** | 2.66 |
| **led_matrix** | 3.57 | 3.04 | 2.63 |
| **compile_blink** | 3.41 | **3.48** | 2.61 |
| **AVERAGE** | **3.39 t/s** | **3.44 t/s** | **2.62 t/s** |

## Analysis
*   **The V3 Peak:** The Optimized V3 engine remains the overall speed leader for short-context generation on the Uno Q hardware, benefiting from specific build-time optimizations in the MPU binary.
*   **The Yazma Baseline:** The original `main` branch (Yazma) performs surprisingly well on simple tasks, essentially matching V3 on average.
*   **Modernization Trade-off:** The Modernized engine (surgical merge) shows a regression in this specific test (~2.62 t/s). While it excelled at complex architectural descriptions (Run 03: 2.60 t/s vs V3 2.33 t/s), it carries more overhead for simpler, high-repetition prompts compared to the older, lighter cores.
*   **Conclusion:** The surgical modernization is optimized for **long-context/complex tasks**, whereas the V3 and Yazma cores remain faster for **short-turn utility tasks**.
