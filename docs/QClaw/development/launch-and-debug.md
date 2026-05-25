# Launching and Debugging the llamaserver Provider

Developer reference for **`pkg/providers/llamaserver`** — the persistent on-device inference provider used by all three QClaw execution paths (Agentic, Direct, TUI Chat). Covers how to verify each layer in isolation and where to look when something breaks.

For general operation instructions see [`setup-walkthrough.md`](setup-walkthrough.md). For architecture context see [`architecture-study-bible.md`](architecture-study-bible.md).

---

## 1. Mental model

```
Agent loop / TUI chat page / qclaw direct
    │
    │  providers.LLMProvider.Chat() / ChatStream() / WarmUp()
    ▼
pkg/providers/llamaserver.Provider              (pkg/providers/llamaserver/provider.go)
    │
    │  ensureServer(ctx, model)                 — called on first Chat/ChatStream/WarmUp
    │    resolveModel(model) → absolute path    — ~/models/<name>[.gguf]
    │    exec.Command(binary, pinned + extra)   — spawn child process
    │    inject LD_LIBRARY_PATH=<lib_path>:...  — for dynamically-linked builds
    │    poll GET /health until 200 OK          — up to 30 s
    │    mark p.initialized = true              — subsequent calls skip spawn
    │
    │  inner openai_compat.Provider             — wraps the live HTTP server
    ▼
HTTP POST 127.0.0.1:<port>/v1/chat/completions
    │  ChatStream: SSE — reads delta chunks, accumulates tool_calls, calls onToken
    │  Chat:       blocks until [DONE]
    ▼
engines/yzma/lib/llama-server                   (b9127, ARMv8.0, CPU-only)
    │  Model: mmap'd once at first /health → stays in RAM across requests
    │  Decode: ~8–11 tok/s on Qwen3.5-0.8B-Q4_0 (Cortex-A53 × 4)
    ▼
LLMResponse { Content, ToolCalls }
```

One server process per `*Provider` instance. The TUI pre-warms via `WarmUp()` at launch; Paths A and B start it on the first `Chat()` call. The child is killed in `Provider.Close()` (or `Stop()`).

---

## 2. Pre-flight checks

Walk these in order before enabling debug logging.

### 2.1 Binary present and executable

```bash
ls -la engines/yzma/lib/llama-server
# expect: -rwxr-xr-x, ~9 MB
LD_LIBRARY_PATH=engines/yzma/lib engines/yzma/lib/llama-server --version 2>&1 | head -3
# version: 9127 (a9883db8e)
# built with GNU 14.2.0 for Linux aarch64
```

Recovery: `cp /home/arduino/ArduinoApps/yzma/lib/llama-server engines/yzma/lib/` then `chmod +x`.

### 2.2 Model present

```bash
ls -la ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf   # ~490 MB
```

Recovery (missing): re-run `make qclaw-setup` or download directly from HuggingFace (see setup-walkthrough §3).

### 2.3 Server can start and respond

Spawn it manually with the same flags the provider uses:

```bash
LD_LIBRARY_PATH=engines/yzma/lib \
  engines/yzma/lib/llama-server \
    -m ~/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf \
    --host 127.0.0.1 --port 8083 \
    -t 4 -c 8192 -np 1 \
    --reasoning off --jinja --log-disable &

# Wait for health (up to 5 min cold)
until curl -sf http://127.0.0.1:8083/health; do sleep 5; done
echo "Server ready"
```

Then send a minimal completion:

```bash
curl -s http://127.0.0.1:8083/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"x","messages":[{"role":"user","content":"Reply with one word: pong"}],"max_tokens":4}' \
  | python3 -m json.tool
```

A healthy response contains `"content": "pong"` (or similar). Kill with `pkill -f llama-server` when done.

### 2.4 Provider-level smoke test

```bash
go test ./pkg/providers/llamaserver/... -run TestProvider -v -count=1 -timeout 30m
```

This exercises the full stack: spawn, health-check, `Chat()`, response decode. A `PASS` means the Go layer and the binary are in sync.

If 2.1–2.3 pass but 2.4 fails, the bug is in the provider Go code.

---

## 3. Debug logging

The provider logs through `pkg/logger`. Enable verbose output:

```bash
QCLAW_DEBUG=1 qclaw direct --model yzma -m "test"
```

On first call the provider logs the spawn command:

```
llamaserver: starting server: engines/yzma/lib/llama-server \
  -m /home/arduino/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf \
  --host 127.0.0.1 --port 8083 -t 4 -c 8192 -np 1 \
  --reasoning off --jinja --log-disable
llamaserver: server ready on port 8083
```

On every subsequent call:
```
llamaserver: POST /v1/chat/completions (stream=true)
llamaserver: response in 11.84s, 83 tokens
```

To replay a failed call, copy the `POST` body from your logs and send it directly with curl (see 2.3).

---

## 4. Common failure modes

### 4.1 `fork/exec …/llama-server: no such file or directory`

The `api_base` in `~/.qclaw/config.json` points to a missing binary. Check:

```bash
cat ~/.qclaw/config.json | python3 -c "import json,sys; [print(e.get('model_name'), e.get('api_base')) for e in json.load(sys.stdin)['model_list']]"
```

Fix: ensure the path matches the actual binary location (`engines/yzma/lib/llama-server`). The provider resolves relative paths from CWD — run `qclaw` from the repo root.

### 4.2 `model_name` / `model` mismatch

`providers.CreateProvider()` uses `agents.defaults.model_name` to find the model_list entry. If `model_name` names a deleted engine, the binary path from that entry is used and fails.

```bash
python3 -c "
import json
c = json.load(open('/home/arduino/.qclaw/config.json'))
print('model:', c['agents']['defaults']['model'])
print('model_name:', c['agents']['defaults']['model_name'])
"
```

Both `model` and `model_name` should be `"yzma"`. Fix: update `model_name` in `~/.qclaw/config.json` to match the engine key.

### 4.3 `llama-server initialization failed: context deadline exceeded`

The health-check loop timed out (default 30 polls × 1 s = 30 s). On a cold Uno Q boot the model mmap can take several minutes. Causes:

- `request_timeout` too short in the model_list entry — set ≥ 1200 s.
- System swap thrashing — `free -h`; cold-start needs ~1.1 GB RSS free.
- Binary failed silently — check if the process is still running: `ps -ef | grep llama-server`.

### 4.4 HTTP 500 `"Context size has been exceeded"`

The `--parallel` flag defaulted to auto (≥2) and divided ctx_size per slot. With `ctx_size=8192` and 4 slots the effective context is ~2048 — too small for the QClaw system prompt. Fix: ensure `"parallel": 1` is in the `extra_body` of the engine entry.

### 4.5 `signal: killed` during inference

OOM kill. Each llama-server peaks ~1.1 GB RSS. Check: `dmesg | grep -i "killed process"`. Mitigation: close other memory-heavy processes; use the 0.6B Q4_0 model (~340 MB) for low-RAM scenarios.

### 4.6 `address already in use` on port 8083

A previous llama-server instance is still running. Kill it:

```bash
pkill -f "llama-server.*8083"
# or find the PID:
ss -tlnp | grep 8083
```

The TUI's pre-warm goroutine correctly waits for `loop.Close()` + `cmd.Wait()` before re-spawning, so this should only appear after an unclean exit.

### 4.7 TUI Chat shows stale engine after config change

The pre-warmed `chatPage` was built from the config at TUI launch time. If you changed `agents.defaults.model` in the TUI and then opened Chat, `openChat()` checks `pre.engineKey == currentEngine` and discards the stale page. If you see the old engine, close and reopen Chat — the fresh page reads the updated config.

---

## 5. Attaching to a running server

```bash
# Find the PID
ps -ef | grep "llama-server" | grep -v grep

# Watch live HTTP traffic (requires sudo / CAP_NET_ADMIN)
sudo tcpdump -i lo -A -s 0 'tcp port 8083'

# Live syscall trace
strace -p <PID> -e trace=network,read,write 2>&1 | grep -v EAGAIN | head -50
```

The server has no debug endpoint, but `GET /props` returns the loaded model name and context size, and `GET /slots` returns per-slot KV state (useful for confirming `-np 1`).

---

## 6. Where to look in the code

| Concern | File | Symbol |
|---|---|---|
| Provider entry point | `pkg/providers/llamaserver/provider.go` | `(p *Provider) Chat`, `ChatStream`, `WarmUp` |
| Server spawn + health-check | `pkg/providers/llamaserver/provider.go` | `ensureServer` |
| Model path resolution | `pkg/providers/llamaserver/provider.go` | `resolveModel` |
| Factory wiring (config → provider) | `pkg/providers/factory_provider.go` | `CreateProviderFromConfig` (`llama-server` case) |
| TUI pre-warm orchestration | `cmd/qclaw-launcher-tui/internal/ui/app.go` | `triggerPrewarm`, `openChat` |
| TUI chat page + preWarm | `cmd/qclaw-launcher-tui/internal/ui/chat.go` | `chatPage.preWarm`, `chatPage.close` |
| Streaming token pipeline | `pkg/providers/llamaserver/provider.go` | `ChatStream` SSE loop |
| Direct path (non-TUI) | `pkg/agent/loop.go` | `ProcessDirectSingleTurnStream` |
| Agentic path (non-TUI) | `pkg/agent/loop.go` | `ProcessAgenticWithProgressStream` |
| TUI chat design rationale | `docs/QClaw/development/tui-chat-design.md` | — |
| Engine binary + .so files | `engines/yzma/lib/` | `llama-server`, `libggml-*.so` |
| Benchmark numbers | `docs/benchmarks/BENCHMARK_SUMMARY.md` | Runs 6–9 |
