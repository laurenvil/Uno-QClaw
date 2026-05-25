# engines/yzma/lib — Yzma b9127 Binaries

## Binary provenance

| Item | Value |
|---|---|
| Source repo | https://github.com/hybridgroup/yzma |
| Release tag | `v1.14.1` |
| Source commit | `a4dbf00c3e5503002c333330147db467aa3a7f99` |
| llama.cpp build | `b9127` |
| Target | aarch64 Linux (Cortex-A53, Qualcomm QRB2210) |
| Backends | Dynamic: CPU (ARMv8/ARMv9 SIMD variants) + RPC |
| Build date | 2026-05-25 |

## Contents

| File | Size | Role |
|---|---|---|
| `llama-server` | 9.0 MB | HTTP inference server (OpenAI-compatible API) |
| `llama-cli` | 1.5 MB | One-shot subprocess inference |
| `libggml-base.so*` | 779 KB | ggml base |
| `libggml-cpu-armv8.*.so` / `libggml-cpu-armv9.*.so` | ~900 KB ea | CPU SIMD kernels |
| `libggml-rpc.so` | 159 KB | RPC backend |
| `libggml.so*` | 76 KB | ggml core |
| `libllama-common.so*` | 4.9 MB | llama common |
| `libllama.so*` | 3.3 MB | llama core |
| `libmtmd.so*` | 1.2 MB | Multi-token multi-dim |

## Performance (QClaw Run 9, pwm_pins)

- `llama-server`: Wall (cold, optimized flags): **12m35s** mean (σ=4s, 3 samples)
- `llama-cli`: **Not viable** — no `--repeat-penalty` defaults in llamacli provider causes
  repetition loop on Qwen 0.8B (see `docs/benchmarks/run9/` and whitepaper §9.2)

## Rebuild / update instructions

```bash
# Download a fresh yzma release archive
curl -L https://github.com/hybridgroup/yzma/releases/download/v1.14.1/\
llama-b9127-bin-ubuntu-arm64.tar.gz -o /tmp/yzma-b9127.tar.gz
tar -xzf /tmp/yzma-b9127.tar.gz -C /tmp/yzma-b9127/
cp /tmp/yzma-b9127/llama-server /tmp/yzma-b9127/llama-cli engines/yzma/lib/
cp /tmp/yzma-b9127/lib*.so* engines/yzma/lib/
```

Or copy from a local yzma build at `~/ArduinoApps/yzma/lib/`.
