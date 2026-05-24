# Benchmark Results: llama-server (Run 02)

**Branch:** `qclaw-llmaCLI-v3`
**Engine:** Optimized V3 Assix Server (`engines/llamacli/mpu/llama-server`)
**Model:** Qwen 3.5 0.8B Q4_0 (`Qwen_Qwen3.5-0.8B-Q4_0.gguf`)
**Date:** Sunday, May 24, 2026

---

## Configuration
*   **Context Size:** 512 tokens
*   **Threads:** 4
*   **GPU Layers:** 0 (CPU Fallback)
*   **Reasoning:** Disabled (`--reasoning off`)

## Performance Metrics

### Cold Run (First Request)
| Metric | Result | Notes |
| :--- | :--- | :--- |
| **Prompt Processing** | **5.59 t/s** | Evaluated 6 tokens in 1.07s |
| **Token Generation** | **3.59 t/s** | Generated 64 tokens in 17.82s |

### Hot Run (Cached Request)
| Metric | Result | Notes |
| :--- | :--- | :--- |
| **Prompt Processing** | **5.38 t/s** | Best of two hot runs |
| **Token Generation** | **3.13 t/s** | Best of two hot runs |

## Analysis
*   **Engine Comparison:** The V3 engine shows nearly identical performance to the modernized engine on the `QClaw-GPU-CLI` branch (~5.5 t/s prompt, ~3.6 t/s gen).
*   **Cache Behavior:** Hot runs did not show the expected performance boost, likely because the prompt (6 tokens) is too small for KV-cache reuse to significantly reduce computation time compared to the overhead of the server response loop.
*   **Hardware Fallback:** Both engines successfully identified and subsequently dropped the **FD702** GPU due to driver-level subgroup limitations.

## Artifacts
*   **Cold Server Log:** `run2/server_v3_cold.log`
