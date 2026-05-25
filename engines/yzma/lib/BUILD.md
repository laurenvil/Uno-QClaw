# engines/yzma/lib — Yzma b9127 Binaries

## Binary provenance

| Item | Value |
|---|---|
| Source repo | https://github.com/hybridgroup/yzma |
| Release tag | `v1.14.1` |
| Source commit | `a4dbf00c3e5503002c333330147db467aa3a7f99` |
| llama.cpp build | `b9127` |
| Target | aarch64 Linux (Cortex-A53, Qualcomm QRB2210) |
| CPU backend | `libggml-cpu-armv8.0_1.so` — ARMv8.0 SIMD (Cortex-A53) |
| Build date | 2026-05-25 |

## Contents

This directory is trimmed to the minimum required for the Arduino Uno Q (ARMv8.0, Cortex-A53). No build is needed — clone the repo and run.

| File | Size | Role |
|---|---|---|
| `llama-server` | 9.0 MB | HTTP inference server (OpenAI-compatible API) — used by QClaw |
| `libggml-base.so*` | 779 KB | ggml base (hard dependency) |
| `libggml-cpu-armv8.0_1.so` | 907 KB | CPU SIMD kernels for Cortex-A53 (dlopen'd at startup) |
| `libggml.so*` | 76 KB | ggml core (hard dependency) |
| `libllama-common.so*` | 4.9 MB | llama common (hard dependency) |
| `libllama.so*` | 3.3 MB | llama core (hard dependency) |
| `libmtmd.so*` | 1.2 MB | multimodal support (hard dependency even for text-only) |

The `.so` files are essential — `llama-server` is dynamically linked against them and will not start without them. The only other dependencies are standard Debian packages (`libssl3`, `libstdc++6`, `libzstd1`, `zlib1g`) present on any base Debian ARM64 install.

## Testing without building

To run the server directly from a fresh clone (no Go build, no compilation):

```bash
# From the repo root — set LD_LIBRARY_PATH so the dynamic linker finds the bundled .so files
LD_LIBRARY_PATH=engines/yzma/lib engines/yzma/lib/llama-server --version
# Expected: version: 9127 (a9883db8e)

# Start the server against a model
LD_LIBRARY_PATH=engines/yzma/lib engines/yzma/lib/llama-server \
  -m ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf \
  --host 127.0.0.1 --port 8083 \
  -t 4 -c 8192 -np 1 \
  --reasoning off --jinja --log-disable

# In a second terminal — verify the server is up
curl -s http://127.0.0.1:8083/health
# Expected: {"status":"ok"}

# Send a test inference request
curl -s http://127.0.0.1:8083/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"local","messages":[{"role":"user","content":"Hello"}],"max_tokens":64}' \
  | python3 -m json.tool
```

QClaw handles `LD_LIBRARY_PATH` automatically via the `lib_path` field in `config.json` — manual export is only needed when testing the binary directly.

## Performance (QClaw Run 9, pwm_pins)

- `llama-server`: Wall (cold, optimized flags): **12m35s** mean (σ=4s, 3 samples)

## Rebuild / update instructions

```bash
# Download a fresh yzma release archive
curl -L https://github.com/hybridgroup/yzma/releases/download/v1.14.1/\
llama-b9127-bin-ubuntu-arm64.tar.gz -o /tmp/yzma-b9127.tar.gz
tar -xzf /tmp/yzma-b9127.tar.gz -C /tmp/yzma-b9127/
cp /tmp/yzma-b9127/llama-server engines/yzma/lib/
cp /tmp/yzma-b9127/lib*.so* engines/yzma/lib/
# Then remove non-ARMv8.0 CPU variants and unused libs (see trim rationale above)
```

Or copy from a local yzma build at `~/ArduinoApps/yzma/lib/`.
