# QClaw v2: Multi-Engine llama-server Plan

This document records the implementation plan for generalizing `llamaserver.Provider` to support multiple llama.cpp builds — the existing assix MPU binary, the freshly-built Surgical (modern ggml-org core), and a fresh Adreno-tuned assix rebuild — all behind the same protocol string and switchable by config.

---

## 1. Motivation

QClaw-v2 currently hardcodes one llama-server binary: the assix pre-compiled `engines/llamacli/mpu/llama-server`. Two other engine binaries already exist on the device but are unreachable from QClaw:

- **Surgical** (`qclaw/llama.cpp/build/bin/llama-server`) — modern ggml-org `llama.cpp` core + assix backend, dynamically linked against sibling `.so` files
- **Adreno-tuned assix** (planned: `engines/llamacli/llama.cpp/build-adreno/bin/llama-server`) — fresh rebuild of the assix source, which already contains FD702 in its OpenCL allowlist and bypasses the missing-subgroups check for Adreno devices

The current binary cannot engage the Adreno 702 because it was built before FD702 support landed in the assix source. The Surgical build uses ggml-org's OpenCL backend (different kernel set), not assix's Adreno-specific one. To benchmark and compare them we need to be able to swap engines without rebuilding QClaw — pure config changes.

---

## 2. Architecture

The existing `llamaserver.Provider` already spawns an arbitrary binary, health-checks it, and proxies through the OpenAI-compatible `/v1/chat/completions` endpoint. The only blocker for the Surgical build is that it dynamically links its own `.so` files, and the provider currently spawns with `cmd.Env = nil` (inherits the parent environment, which has no `LD_LIBRARY_PATH` pointing at the build/bin directory).

The change is **one new option on the provider**, threaded through the factory and config:

```
config.json model_list[].extra_body["lib_path"]
        │
        ▼
factory_provider.go : llama-server case
        │
        ▼
llamaserver.WithLibraryPath(path)
        │
        ▼
llamaserver.Provider.libraryPath
        │
        ▼
ensureServer() : cmd.Env = "LD_LIBRARY_PATH=<libraryPath>:..."
```

No protocol string changes, no new provider type, no fallback chain rework. Any future llama-server variant can be added by appending one entry to `model_list`.

---

## 3. Phases

### Phase A — Surgical Build as a Provider

**Code changes**

| File | Change |
|---|---|
| `pkg/providers/llamaserver/provider.go` | Add `libraryPath` field, `WithLibraryPath(string) Option`, prepend to `LD_LIBRARY_PATH` in `ensureServer` before `cmd.Start()` |
| `pkg/providers/factory_provider.go` | In `llama-server` case, parse `extra_body["lib_path"]` and pass via `WithLibraryPath` |
| `config/qclaw.config.json` | Replace single `model_list` entry with named entries `assix-mpu` and `surgical` |
| `~/.qclaw/config.json` | Same change for the local config |

**Distinct ports** (`8080` for assix-mpu, `8081` for surgical, `8082` for adreno) prevent collisions if engines ever run simultaneously.

**Verification**

1. Build with `GO=/home/arduino/go-installs/go/bin/go make build && make install`
2. Smoke test: `qclaw direct --model surgical -m "ping"` — confirm no `error while loading shared libraries` (proves `LD_LIBRARY_PATH` works)
3. Capture OpenCL init from stderr — expected: `drop unsupported device` (Surgical uses ggml-org backend, not Adreno-aware)

**Benchmark**

Three controlled invocations on the `pwm_pins` prompt (short, factual, no tool loop):

```
qclaw direct --model surgical    -m "Which pins on the Uno Q can do PWM?"   # cold
qclaw direct --model surgical    -m "Which pins on the Uno Q can do PWM?"   # warm (page cache)
qclaw direct --model assix-mpu   -m "Which pins on the Uno Q can do PWM?"   # baseline
```

Record cold wall, warm wall, and generation tok/s. Expected: parity with assix-mpu on CPU.

### Phase B — Adreno-Tuned assix Build

**Build the assix source fresh**

The source already has FD702 in its detection block (`ggml-opencl.cpp:3599`) and bypasses the subgroups drop for Adreno (`ggml-opencl.cpp:3712`). The current build artifact is identical to `mpu/llama-server` (same SHA-256) — meaning it predates those source changes. A fresh build will produce a different binary that exercises the FD702 path.

```bash
cd engines/llamacli/llama.cpp
rm -rf build-adreno
cmake -B build-adreno \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_OPENCL=ON \
  -DGGML_OPENCL_USE_ADRENO_KERNELS=ON \
  -DLLAMA_BUILD_SERVER=ON
cmake --build build-adreno -j4 --target llama-server
```

**Estimated build time: 25–40 minutes** on 4 Cortex-A53 cores.

**Verify** the fresh binary differs from the cached one:

```bash
sha256sum engines/llamacli/mpu/llama-server \
          engines/llamacli/llama.cpp/build-adreno/bin/llama-server
# expect mismatch
```

**Add as third entry** in `model_list` with `lib_path` pointing at the build's `bin/` directory (harmless if statically linked, load-bearing if not).

**Benchmark and inspect OpenCL init**

```bash
qclaw direct --model assix-adreno -m "Which pins on the Uno Q can do PWM?" 2>stderr.log
grep -E "ggml_opencl|drop|Adreno|FD702|kernels optimized" stderr.log
```

Three possible outcomes:

| Outcome | Signal | Next step |
|---|---|---|
| GPU engaged | `using kernels optimized for Adreno`, no drop, tok/s ≥ CPU | Done |
| Kernels fail to compile | `clBuildProgram` errors | Patch kernel source for rusticl, or fall back to compat path |
| GPU active but slow | Like Vulkan path (0.25 t/s) | Memory transfer bottleneck on unified memory; not worth pursuing |

### Phase C — Document and Decide

Write `docs/benchmarks/run6/three-engine-comparison.md` covering all three engines on the `pwm_pins` prompt, and update `docs/benchmarks/BENCHMARK_SUMMARY.md` with the new data.

---

## 4. Defaults

| Decision | Choice |
|---|---|
| Phase B build | Proceed (~30 min blocking, but it's the only way to test the Adreno hypothesis) |
| Default model after Phase A | Keep `assix-mpu` — switch only if benchmarks justify it |
| Binary commitment | Defer — add `scripts/build-engines.sh` for reproducibility, commit binaries only if one engine wins decisively |
| Benchmark prompt | `pwm_pins` (single short prompt) — full 9-prompt battery is 90 min × 3 engines, run only if results need ratification |

---

## 5. File Inventory (expected)

| File | Changes | Purpose |
|---|---|---|
| `pkg/providers/llamaserver/provider.go` | +6 / −1 | `libraryPath` field, `WithLibraryPath` option, env injection |
| `pkg/providers/factory_provider.go` | +3 | Parse `extra_body["lib_path"]`, pass to provider |
| `config/qclaw.config.json` | +20 / −10 | Three-engine `model_list` |
| `~/.qclaw/config.json` | +20 / −10 | Same (not in repo, but tracked here) |
| `scripts/build-engines.sh` | +30 (new) | Reproducible build recipe for surgical + adreno |
| `docs/benchmarks/run6/three-engine-comparison.md` | (new) | Run 6 results |
| `docs/benchmarks/BENCHMARK_SUMMARY.md` | +3 | Add Run 6 row |
