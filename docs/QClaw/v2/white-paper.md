# Technical White Paper: QClaw Inference Engine Modernization & Integration

## Executive Summary
This paper details the technical evolution and surgical integration of the inference engine for the QClaw project on the Arduino Uno Q hardware. Over three distinct build phases, we successfully transitioned from a fragmented, baseline engine to a modernized, high-performance hybrid that supports latest-generation model architectures (Llama 3, Qwen 3.5) while preserving hardware-specific OpenCL optimizations.

---

## 1. Build Process I: The Adreno-Optimized Hybrid (Branch: `v3`)

### Objective
To validate the performance of the Assix-optimized CPU core when combined with the "Wang" OpenCL fixes specifically targeting the Adreno 702 (FD702) GPU found on the Uno Q.

### Technical Implementation
*   **Surgical Backend Patching:** Manually modified `ggml-opencl.cpp` to recognize the `FD702` device string, which is typically dropped by standard OpenCL drivers on Linux (rusticl).
*   **Inference Loop Migration:** Transitioned from the one-shot `llama-cli` to a persistent `llama-server` architecture.
*   **Result:** Achieved 2x performance gains over the Yazma baseline on the CPU (~7.5 t/s prompt). GPU benchmarks confirmed that while the kernels were recognized, the `rusticl` driver's lack of OpenCL 3.0 subgroups (specifically `cl_khr_subgroups`) remains a bottleneck for native GPU execution.

---

## 2. Build Process II: The Baseline Diagnostic (Branch: `QClaw-GPU-CLI`)

### Objective
To verify and document the "Clean Upstream" state of the Assix engine replica provided as a reference baseline.

### Technical Findings
*   **Build Failure Analysis:** The initial build attempt failed with `fatal error: models/models.h: No such file or directory`.
*   **Dependency Distinction:** Investigation revealed a critical architectural mismatch. The repository contained a root `models/` directory for runtime weight files (.gguf), but the build system (`CMakeLists.txt`) required a source directory `llama.cpp/src/models/` containing the C++ architecture implementations.
*   **Baseline State:** Confirmed the Assix baseline was a "headless" engine—containing the core logic but lacking the specific mathematical blueprints for individual model families.

---

## 3. Build Process III: The Surgical Modernization (Final Result)

### Objective
To fix the baseline build and enable support for modern models (like Qwen 3.5) without adopting the aggressive Wang GPU patches, thereby maintaining the stable Assix OpenCL logic.

### Integration Strategy: The "Surgical Merge"
*   **Model Blueprint Integration:** Injected the `src/models/` and `tools/mtmd/models/` directories from the Wang fork. These files are backend-agnostic C++ math definitions that do not touch GPU logic.
*   **Core Synchronization:** Build failures during Step 1 revealed that the Assix core engine (specifically `llama-model.cpp`) was too old to handle the new modular architecture. We synchronized the core `src/`, `include/`, `common/`, and `tools/` directories from the Wang fork.
*   **Backend Preservation:** We intentionally **excluded** `ggml/src/ggml-opencl.cpp/h` from the synchronization. This kept the Assix OpenCL kernels and buffer management intact while upgrading the rest of the software around it.

### Connectivity & Architectural Result
The final build successfully linked `llama-cli` and `llama-server`. The integration now connects:
1.  **Direct Path Execution:** The Go agent binary communicates natively with the updated engine.
2.  **Persistent Server Connectivity:** The Go provider manages a persistent `llama-server` instance, eliminating one-shot latency.
3.  **Modern Architecture Support:** The engine can now register and run Llama 3 and Qwen 3.5 models on the CPU, with an OpenCL fallback for standard operations.

---

## 4. Summary of Integrated Components

| Component | Origin | Role |
| :--- | :--- | :--- |
| **OpenCL Backend** | **Assix** | Hardware-specific GPU kernels and device management. |
| **Model Blueprints** | **Wang** | Mathematical definitions for modern architectures (Llama3/Qwen). |
| **Core Engine** | **Wang (Sync)** | Memory management, batching logic, and public API. |
| **Build System** | **Wang (Sync)** | CMake configuration for modern parallel builds. |
| **Inference Loop** | **QClaw Go** | Agentic framework and persistent server management. |

## Conclusion
The current state of the `QClaw-GPU-CLI` branch represents a "Best-of-Both-Worlds" configuration. By surgically upgrading the engine's architectural support while anchoring it to the Assix GPU backend, we have provided the hardware with the ability to run 2026-era models with 2025-era optimized drivers.
