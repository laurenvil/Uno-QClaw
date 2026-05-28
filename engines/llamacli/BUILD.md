# QClaw-GPU-CLI: Adreno Optimized OpenCL Build

This branch contains the modernized `llama.cpp` engine with critical kernels required for the Adreno 702 GPU (FD702) when running in "no-subgroups" (noshuffle) mode.

## Why this build works

The standard `llama-wang` and upstream builds often crash with `GGML_ASSERT(0)` on the first decode when running on rusticl/FD702. This is because those environments lack subgroup support and fall back to the "noshuffle" path, which is missing optimized Q4_0 kernels in many versions.

This build includes:
- `gemv_noshuffle_q4_0_f32.cl`
- `gemv_noshuffle_q4_0_f32_spec.cl`
- `gemm_noshuffle_q4_0_f32.cl`

These kernels provide the necessary dispatch targets for Q4_0 inference on the Adreno 702.

## Applied Patches
- **Adreno 702 (FD702) Detection:** Patched `llama.cpp/ggml/src/ggml-opencl/ggml-opencl.cpp` to recognize the `FD702` device string.

## Build Configuration
```bash
mkdir build && cd build
cmake .. -DGGML_OPENCL=ON -DCMAKE_BUILD_TYPE=Release \
-DOpenCL_INCLUDE_DIR=/home/arduino/ArduinoApps/opencl-headers/ \
-DOpenCL_LIBRARY=/usr/lib/aarch64-linux-gnu/libOpenCL.so.1 \
-DBUILD_SHARED_LIBS=OFF
make -j4 llama-cli llama-server
```

## Binary Status
Located in `mpu/`:
- **llama-cli**: Static, OpenCL-enabled
- **llama-server**: Static, OpenCL-enabled
