# Run 6 — Four-Engine Comparison on FD702 (rusticl)

**Hardware:** Arduino Uno Q · Qualcomm QRB2210 · 4× Cortex-A53 · 4 GB LPDDR4X
**Driver:** Mesa rusticl 25.2.6 · OpenCL 3.0 on Adreno 702 (reported as `FD702`)
**Model:** `Qwen_Qwen3.5-0.8B-Q4_0.gguf`
**Prompt:** `"Which pins on the Uno Q can do PWM?"` (10 input tokens)
**Date:** 2026-05-24

This run tests the new `llamaserver.WithLibraryPath` option (commit `ebadf10`) and exercises four engine builds through the same provider code path, switching purely by `--model` flag.

---

## Results Table

| Engine | Binary | Wall | Response | OpenCL outcome |
|---|---|---|---|---|
| **assix-mpu** ⭐ | `engines/llamacli/mpu/llama-server` (16 MB, static, aca9a0f) | 17m54s | 427 chars ✅ | `drop unsupported device` — CPU fallback |
| **surgical** | `llama.cpp/build/bin/llama-server` (9.8 MB, dynamic, ggml-org 832d383) | crash @ 57s | none | `enabling no-subgroups compatibility mode for FD702` → `GGML_ASSERT(0) failed at ggml-opencl.cpp:6710` mid-decode |
| **assix-adreno** | `engines/llamacli/llama.cpp/build-adreno/bin/llama-server` (9.8 MB, dynamic, aca9a0f fresh) | hung (killed) | none | Adreno-specific kernels loaded, then `kernel compile error: use of undeclared identifier 'sub_group_reduce_add'` — server aborted, qclaw blocked on dead-server chat request |
| **yzma** | `yzma/lib/llama-server` (9.0 MB, dynamic, hybridgroup b9127) | 16m46s | HTTP 500 ❌ | No OpenCL backend — RPC + CPU only; server returned `"Context size has been exceeded"` after 16m of decode |

⭐ = currently active in QClaw-v2 config

---

## What Each Outcome Tells Us

### assix-mpu — the only build that actually runs to completion

The pre-compiled MPU binary drops FD702 by the original (pre-FD702-allowlist) device-name check, falls back to CPU, and produces a correct answer. 17m54s is cold-cache; warm steady-state is ~3.4 t/s per Run 5. **This remains the only viable inference path on this hardware today.**

### surgical — modern ggml-org core, broken on FD702

The Surgical build's source (laurenvil/Uno-QClaw in-tree llama.cpp) has updated device detection that **does not drop FD702**. Instead it enables `no-subgroups compatibility mode` — building kernels with a compat prelude. The kernels compile, but at first decode `GGML_ASSERT(0)` fires inside `libggml-opencl.so`. The compat prelude isn't a complete polyfill — at least one op routes to code that asserts unconditionally on devices without subgroup support.

This is a llama.cpp upstream issue, not anything QClaw can fix in Go.

### assix-adreno — fresh rebuild with FD702 allowlist + Adreno kernels

The freshly-built assix binary (commit `aca9a0f` source, built today) has both:
- **FD702 in the Adreno detection block** → `using kernels optimized for Adreno (GGML_OPENCL_USE_ADRENO_KERNELS)` ✅
- **Subgroup extension check bypassed** for Adreno devices → `continuing experimentally` ✅

Then kernel compilation begins, and immediately hits:

```
input.cl:6:26: warning: unsupported OpenCL extension 'cl_khr_subgroups' - ignoring
input.cl:108:27: error: use of undeclared identifier 'N_SIMDGROUP'
input.cl:108:41: error: use of undeclared identifier 'get_sub_group_id'
input.cl:156:9:  error: use of undeclared identifier 'sub_group_reduce_add'
...
Error executing LLVM compilation action.
```

**The blocker isn't the device-name allowlist or the extension check** — those are now bypassed. It's that the Adreno kernel source code itself calls `get_sub_group_id`, `get_sub_group_local_id`, and `sub_group_reduce_add` as direct OpenCL C builtins. rusticl's compiler honors the `pragma` that says the extension is unsupported (per spec — `unsupported OpenCL extension 'cl_khr_subgroups' - ignoring`), then refuses to recognize the now-undeclared builtins. The Adreno-specific kernels structurally depend on subgroup operations.

The server died after the kernel compile error. qclaw's healthcheck briefly saw a response (the HTTP listener may have come up before the kernel-load failure), then hung 7 min waiting for a chat response from the dead server until manually killed.

### yzma — older hybridgroup b9127 build, no OpenCL backend

Loaded cleanly (RPC + CPU armv8 backends, no OpenCL attempted), passed the health check, and processed for 16m46s before returning HTTP 500 `"Context size has been exceeded"`. The model decoded ~3300 tokens at ~3.3 t/s — consistent with its Run 5 average — but never emitted EOS, eventually exhausting the 8192-token context window allocated for the request.

The Run 5 9-prompt battery captured yzma at 3.39 t/s avg using shorter outputs (n_predict=128); here with the default 2048 max_tokens and the model failing to emit a stop token, it ran into the context wall. **The b9127 chat template handling differs from the modern assix server's** — possibly mismatched EOS token configuration or missing reasoning-suppression flag (yzma doesn't support `--reasoning off`).

For a fair comparison yzma would need either a tighter max_tokens cap (e.g. n_predict=256) or a corrected chat template. Treat the 16m46s number here as "ran but failed to produce output" rather than as a tok/s measurement.

---

## Validation of Phase A Code

| Behavior | Status |
|---|---|
| `WithLibraryPath` option threads from config through factory to provider | ✅ |
| `LD_LIBRARY_PATH` correctly prepended in `ensureServer` before `exec.Command.Start` | ✅ confirmed by both surgical and adreno binaries loading their `.so` files (no `error while loading shared libraries`) |
| Distinct `--model` selects distinct binaries | ✅ confirmed by binary paths in `provider.go:363` log |
| Distinct ports (8080/8081/8082) prevent collision | ✅ |
| Fallback when server crashes | ❌ **bug found** — when llama-server dies mid-request, qclaw hangs for `request_timeout` (default 20 min) instead of detecting the dead process. Worth a future fix: `cmd.Process.Signal(0)` ping or a goroutine watching `cmd.Wait()` |

---

## Conclusion

| Question | Answer |
|---|---|
| Can `llamaserver.Provider` host multiple engine builds via `--model`? | **Yes**, plumbing works end-to-end across four engines |
| Does the Surgical build engage FD702? | Yes, then crashes at decode |
| Does the Adreno-tuned assix build engage FD702? | Yes, then crashes at kernel compile (subgroup builtins in kernel source) |
| Does yzma work via the new provider? | Server starts and processes correctly, but the b9127 chat template + missing reasoning-off support cause the model to not emit EOS → context overflow at 16m46s |
| Is there a viable GPU path on this hardware today? | **No** — every OpenCL backend on this device structurally requires subgroup builtins that rusticl can't provide. The Vulkan path was already shown to engage but at 0.25 t/s (unusable) |
| Should assix-mpu remain default? | **Yes**, no contender beats it |

The structural blocker is **rusticl's lack of `cl_khr_subgroups`**, not anything in QClaw or the engine selection logic. Two paths exist beyond this run:

1. **Patch the Adreno kernels** to use workgroup-level reductions instead of subgroup reductions (large diff; would need to be upstreamed)
2. **Wait for rusticl** to implement `cl_khr_subgroups` (Mesa tracking issue, no ETA)

The Vulkan path via Turnip remains the only working GPU offload, and is still too slow at the matmul level (memory bandwidth bound on unified memory).
