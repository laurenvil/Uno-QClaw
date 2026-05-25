# engines/llamacli/mpu — assix-mpu Build

## Binary provenance

| Item | Value |
|---|---|
| Source repo | https://github.com/assix/Arduino-UnoQ-Optimized-Llama-CLI |
| Build branch | `QClaw-GPU-CLI` (includes `llama.cpp/src/models/` headers) |
| Source commit | `aca9a0f60e8a82b6676be7b61589530b9a7303f4` |
| llama.cpp tag | `b9099-5d5d2e15d` |
| Target | aarch64 Linux (Cortex-A53, Qualcomm QRB2210) |
| Backends | Static: libllama + libggml + OpenCL (→ CPU fallback on Mesa rusticl) |
| Binary size | ~16 MB (statically linked) |
| Build date | 2026-05-23 |

## Performance (QClaw Run 9, pwm_pins)

- TG: **3.87 t/s** peak, **3.44 t/s** average (9-prompt battery)
- Wall (cold, optimized flags): **12m26s** mean (σ=2s, 3 samples)
- Beats yzma by ~8 s on the same prompt after optimization pass

## Rebuild instructions

```bash
git clone https://github.com/assix/Arduino-UnoQ-Optimized-Llama-CLI.git assix-build
cd assix-build
git checkout QClaw-GPU-CLI
# Build for aarch64 (cross-compile or on-device)
mkdir build-mpu && cd build-mpu
cmake .. -DGGML_OPENCL=ON -DCMAKE_BUILD_TYPE=Release
make -j4 llama-server llama-cli
cp bin/llama-server bin/llama-cli /path/to/qclaw/engines/llamacli/mpu/
```

## OpenCL status on Uno Q

The statically-linked OpenCL backend tries to compile Adreno-specific kernels at init.
Mesa rusticl 25.2.6 does not implement `sub_group_reduce_add`, so init fails.
The binary falls back to CPU automatically via `GGML_OPENCL_PLATFORM=none` env var
(injected by the QClaw llamacli provider).

**Note:** `llama-cli` (not `llama-server`) from this build has no CPU fallback when
OpenCL init fails. Use `yzma/lib/llama-cli` for the llama-cli direct path instead.
