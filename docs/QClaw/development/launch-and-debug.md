# Launching and Debugging the llama-cli Provider

A developer's quick reference for the **`qclaw-llamaCLI` track**: how
`pkg/providers/llamacli` actually drives `engines/llamacli/mpu/llama-cli`
end-to-end, how to verify each layer in isolation, and where to look when
something breaks.

If you just want to *run* QClaw, see
[`setup-walkthrough.md`](setup-walkthrough.md). This file is for people
who need to *see inside* the provider — diff a regression, attach a
debugger, isolate a failure between the agent loop and the inference
subprocess, or port the same pattern into a sibling track.

---

## 1. Mental model

```
agent loop / channel
    │
    │  protocoltypes.Message[], tools[], model, options
    ▼
llamacli.Provider.Chat(ctx, ...)               (pkg/providers/llamacli/provider.go)
    │
    │  1. resolveModel(...)        → absolute path under ~/models/
    │  2. renderPrompt(...)        → ChatML transcript, single string
    │  3. buildGrammar(tools)      → GBNF: text envelope OR tool envelope
    │  4. exec.CommandContext(...) → fork+exec the binary
    │
    ▼
engines/llamacli/mpu/llama-cli                 (assix snapshot, llama.cpp b9099)
    │
    │  -m <model>  -p <prompt>  --grammar <gbnf>
    │  -c <ctx> -t <threads>  --temp <T>  -n <max_tokens>
    │  -st  --reasoning off
    │
    │  mmap GGUF (≈10 s cold, ≈0 s warm-cache)
    │  compile GBNF        (≈100 ms)
    │  prefill prompt      (10.6 t/s on Uno Q for 0.8B Q4_0)
    │  decode response     (~8.8 t/s warm short; ~5 t/s sustained)
    │  emit envelope JSON  → stdout
    │  exit
    │
    ▼
extractJSON(stdout) → parseEnvelope(payload)   (pkg/providers/llamacli/provider.go)
    │
    │  envelope shape: {"text":"…"}  OR  {"tool_call":{"name":…, "arguments":{…}}}
    ▼
LLMResponse{ Content, ToolCalls, ... }
```

Every `Chat()` is **one process**. There is no daemon, no port, no shared
context across calls. If two `Chat()` calls happen concurrently you have
two `llama-cli` processes (each peaking ~1.1 GB RSS) racing for the four
A53 cores.

---

## 2. Pre-flight: five things to verify in order

When QClaw isn't responding, walk these checks **before** turning on debug
logging — they isolate the failure to a single layer in seconds.

### 2.1 Binary present and executable

```bash
ls -la engines/llamacli/mpu/llama-cli
# must be -rwxr-xr-x and ~12 MB
./engines/llamacli/mpu/llama-cli --version 2>&1 | head -2
# version: 9099 (5d5d2e15d)
# built with GNU 13.3.0 for Linux aarch64
```

Recovery: `git submodule update --init --recursive engines/llamacli`. If
the file is on disk but not executable, `chmod +x` it (some clone tools
on weird filesystems strip the exec bit).

### 2.2 Model present and resident

```bash
ls -la ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf   # ~490 MB
# Optional: check page-cache residency
vmtouch ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf  # apt install vmtouch
```

Recovery (missing): see [setup-walkthrough.md §3](setup-walkthrough.md#step-3-download-the-ai-model).
Recovery (cold cache, want warm): `cat ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf > /dev/null` pulls it into the page cache and the next `Chat()` skips the ~10 s mmap cost.

### 2.3 Binary can decode end-to-end on its own

This is the *most useful* single check — it isolates the inference
subprocess completely:

```bash
./engines/llamacli/mpu/llama-cli \
  -m ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf \
  -p "Reply with one word: pong" \
  -st --no-warmup --reasoning off \
  -c 2048 -t 4 -n 8 --temp 0.0 2>&1 | tail -20
```

A healthy run prints something like:

```
pong<|im_end|>
[ Prompt: 10.6 t/s | Generation: 8.8 t/s ]
```

Common failures and what they mean:

| Symptom | Meaning |
|---|---|
| Hangs at `>` prompt, no output | You forgot `-st` (or `--single-turn`); the binary dropped into interactive mode. |
| `Unsupported GPU: FD702 / drop unsupported device.` | Normal on `qclaw-llamaCLI`. The binary falls back to CPU; throughput numbers above still apply. |
| `Failed to initialize samplers: std::exception` | You passed `--json-schema` (broken in this fork). Use `--grammar` with hand-written GBNF — that's what the provider does. |
| Segfault | The binary itself is broken (rare). Re-pull the submodule. |
| Token rate <2 t/s | Either thermal throttling, swap thrashing (`free -h`), or page cache cold (see 2.2). |

### 2.4 Grammar parses

The provider's hand-written GBNF lives in `buildGrammar()` and accepts
two shapes:

```
text-envelope  → {"text": "..."}
tool-envelope  → {"tool_call":{"name":"<one-of>","arguments":{...}}}
```

You almost never need to touch it; if you do, paste the candidate grammar
into the binary directly:

```bash
./engines/llamacli/mpu/llama-cli \
  -m ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf \
  -p "say hi" \
  --grammar 'root ::= "{\"text\":\"" [a-zA-Z0-9 .,!?]+ "\"}"' \
  -st --reasoning off -c 256 -t 4 -n 32 --temp 0.0
```

If the binary prints `Failed to parse grammar` you have a GBNF syntax
error; the binary's parser is upstream llama.cpp's and the error message
points to the offending rule.

### 2.5 Provider-level smoke

The integration test exercises the entire stack — prompt rendering,
grammar build, subprocess spawn, stdout capture, envelope parse,
`LLMResponse` decode:

```bash
go test -tags=integration -run TestIntegration_LlamaCLIText \
  -v -count=1 -timeout 10m ./pkg/providers/llamacli/
```

A successful run ends with `--- PASS` and a `Chat()` walltime of ~14 s
cold or ~10 s warm. A `TestIntegration_LlamaCLIToolCall` companion
verifies the tool envelope path.

If 2.1–2.4 pass and 2.5 fails, the bug is in the provider Go code, not in
the inference engine.

---

## 3. The bench script

`scripts/bench-llamacli-provider.sh` is the **golden reproducer**. It
captures all five layers above in three phases:

```bash
bash scripts/bench-llamacli-provider.sh
```

| Phase | What it measures | Pass criteria |
|---|---|---|
| **A.1–A.3** | Direct binary t/s at n=16/64/128 decode | warm pp ≈ 10.6, tg ≈ 8.8 (short) / ~4.8 (sustained) |
| **B.1** | Cold start (mmap + grammar compile + 1 token) | ~12 s wall |
| **C.1–C.2** | Go provider end-to-end (text + tool envelopes) | text ≈ 14 s, tool ≈ 20 s cold |

Raw output lands in `docs/GPU/benchmark-raw.txt`; the curated report is
[`docs/GPU/benchmark-results.md`](../../GPU/benchmark-results.md). Any
regression you suspect should reproduce in one of these phases or it
isn't in the provider.

---

## 4. Provider debug logging

Run the agent with verbose output:

```bash
./build/qclaw gateway --debug
```

For every `Chat()` the provider logs:

```
llamacli: exec /home/arduino/ArduinoApps/QClaw/engines/llamacli/mpu/llama-cli \
  -m /home/arduino/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf \
  -st --reasoning off \
  --grammar 'root ::= …' \
  -c 2048 -t 4 \
  -p '<|im_start|>system\n…<|im_end|>\n<|im_start|>user\n…<|im_end|>\n<|im_start|>assistant\n' \
  -n 512 --temp 0.0
llamacli: exit 0 in 14.331s (stdout 312 B, stderr 4096 B)
```

If exit ≠ 0 the provider returns the wrapped error including the
truncated last 1000 B of stderr — usually enough to spot the cause
(missing model, malformed grammar, OOM kill).

To replay a specific failed call by hand, copy the `exec …` line and run
it directly (drop the `-p` value into a file if it's too long for
`bash -c`).

---

## 5. Common failure modes

### 5.1 `llama-cli exec failed: signal: killed`

The kernel OOM-killed the subprocess. Each `llama-cli` peaks at ~1.1 GB
RSS; on a 4 GB Uno Q two concurrent `Chat()` calls plus the agent +
gateway + the page cache can hit the OOM threshold. Mitigations: serialise
calls at the channel layer, or use the 0.6B Q4_0 model (~340 MB RSS) for
high-concurrency loads.

### 5.2 `context deadline exceeded` / `signal: killed: context canceled`

The Go-side timeout fired. Default `p.timeout` is set via
`WithTimeout(...)` at construction. Bump it in
`~/.qclaw/config.json` (`request_timeout: 1200`) — cold-load + a 200-tok
decode can easily exceed 30 s on this board.

### 5.3 `parsing llama-cli output: invalid character 'A' …`

The binary emitted free-form text before the JSON envelope (usually
because the grammar didn't engage — check that `--grammar` is being
passed; some forks of `llama-cli` ignore unknown flags silently). The
provider's `extractJSON` tries to find the first balanced JSON object in
stdout; if even that fails it returns the truncated stdout in the error
so you can see what the model actually said.

### 5.4 Tool envelope arrives with wrong tool name

The grammar `tool-name` rule is a literal alternation of registered tool
names — if a tool isn't in `tools[]`, the model literally cannot emit it.
Confirm `tools[]` reaching `Chat()` matches the agent's
`ToolRegistry.Names()`. (The agent loop in `pkg/agent/loop.go` builds
this list once per turn.)

### 5.5 Model reasons before answering despite `--reasoning off`

`--reasoning off` is belt-and-braces. The actual suppressor is `/no_think`
in `workspace/SOUL.md`'s first line. If you customised `SOUL.md`, restore
the directive — without it, Qwen 3.5 spends ~300 tokens of `<think>`
content before the constrained envelope, easily pushing wall time past
30 s on a Q4_0 0.8B.

---

## 6. Attaching gdb / strace

For deep dives — usually only useful when the binary itself hangs.

```bash
# Trace a single Chat() syscall-by-syscall
strace -f -o /tmp/llama-trace.log \
  ./engines/llamacli/mpu/llama-cli \
  -m ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf \
  -p "test" -st --reasoning off -c 256 -t 4 -n 4 --temp 0.0
less /tmp/llama-trace.log     # look for ENOMEM, EFAULT, mmap returning -1
```

```bash
# Live-attach to a hung agent's child subprocess
ps -ef | grep llama-cli | grep -v grep   # find PID
sudo gdb -p <PID>
(gdb) bt          # see where it's stuck
(gdb) thread apply all bt   # all threads
```

The binary is stripped (assix doesn't ship symbols) — backtraces will be
mostly hex addresses inside `libllama.so` linked statically. For better
symbols, rebuild from `engines/llamacli/llama.cpp/` with
`-DCMAKE_BUILD_TYPE=RelWithDebInfo` and substitute the binary; the assix
source tree is enough to do this without checking out anything else.

---

## 7. Where to look in the code

| Concern | File | Function |
|---|---|---|
| Provider entry point | `pkg/providers/llamacli/provider.go` | `(p *Provider) Chat(...)` |
| ChatML prompt rendering | `pkg/providers/llamacli/provider.go` | `renderPrompt(messages)` |
| GBNF grammar construction | `pkg/providers/llamacli/provider.go` | `buildGrammar(tools)` |
| Stdout JSON extraction | `pkg/providers/llamacli/provider.go` | `extractJSON(s)` |
| Envelope decode | `pkg/providers/llamacli/provider.go` | `parseEnvelope(payload)` |
| Unit tests (no binary) | `pkg/providers/llamacli/provider_test.go` | `TestRenderPrompt_ChatML`, … |
| Integration tests (real binary) | `pkg/providers/llamacli/provider_integration_test.go` | `TestIntegration_LlamaCLIText`, `TestIntegration_LlamaCLIToolCall` |
| Launch script | `scripts/qclaw-launch.sh` | top-level driver |
| Reproducer | `scripts/bench-llamacli-provider.sh` | benchmarks all phases |
| Architecture writeup | `docs/GPU/llama-cli-provider-whitepaper.md` | end-to-end design rationale |
| Benchmark numbers | `docs/GPU/benchmark-results.md` | V1 numbers behind §3 above |

---

## 8. Related tracks

| Branch | What it adds | Where to read |
|---|---|---|
| `QClaw-Client-V2` | OpenCL (Wang + v4.4) and Vulkan (Sensai v5) GPU variants alongside this CPU baseline | `docs/GPU/v2/benchmark-results.md` |
| `QClaw-GPU-CLI` | Broader GPU experiment notes | branch HEAD |
| `QClaw-v2` | Direct path re-enabled as native Go (`ProcessDirectSingleTurn` / `qclaw direct`); benchmark runs 1–5 under `docs/QClaw/v2/benchmarks/` | `docs/GPU/V3/direct-path-implementation.md` |
