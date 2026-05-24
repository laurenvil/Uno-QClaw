# QClaw v2: CLI UX Improvements — Thinking Indicator, Progress Messages, Elapsed Time, and Token Streaming

This document records the five user-experience improvements added to the QClaw CLI in commit `966abfa`. Before this change, the user typed a question and stared at a blank terminal until the agent finished — sometimes 30 s, sometimes 20 min. The change set replaces that with live feedback at every stage.

---

## 1. The Problem

The QClaw CLI is synchronous: the user calls `ProcessDirect()` or `ProcessDirectSingleTurn()`, the call blocks until the agent loop completes, and the final string is returned for printing. The agent loop itself may run for many seconds (the model spawns a subprocess that mmaps a 490 MB GGUF, decodes at ~8 t/s on a Cortex-A53, and possibly chains multiple tool calls) — but none of that is visible to the user. The terminal looks frozen.

The five improvements below address four perceived problems:

| Problem | Symptom | Improvement |
|---|---|---|
| "Is it dead?" | Long silence between question and answer | Thinking indicator (spinner) |
| "How long has this been running?" | No sense of progress | Elapsed-time display |
| "What's it doing right now?" | Invisible tool calls during agentic runs | Tool-call / iteration progress messages |
| "Why am I waiting for the whole answer?" | Final response appears in one block | Token streaming (direct path only) |

Telegram's typing indicator was already wired (`pkg/channels/telegram/telegram.go:249`) — this commit brings parity to the CLI.

---

## 2. Architecture

The five features share a common plumbing pattern: **optional callbacks threaded from the CLI through the agent loop down to the provider**. No new daemons, no IPC, no extra goroutines on the hot path — just one channel of feedback flowing back up the call stack as work happens.

```
┌──────────────────────────────────────────────────────────────────┐
│ cmd/qclaw/internal/agent/                                         │
│                                                                   │
│   spinner.go         ← animated Braille frames + elapsed time     │
│       │ runs in its own goroutine on stderr                       │
│       │                                                            │
│   direct.go ─→ runDirectTurn()                                    │
│       │  • startSpinner("QClaw is thinking…")                     │
│       │  • onToken: stop spinner on first token, print rest live  │
│       │  • call ProcessDirectSingleTurnStream(..., onToken)       │
│       │                                                            │
│   helpers.go ─→ runAgenticTurn()                                  │
│          • startSpinner("QClaw is thinking…")                     │
│          • progress callback: prints "🔧 Calling X" / "✓ done"    │
│          • call ProcessDirectWithProgress(..., onProgress)        │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ pkg/agent/loop.go                                                 │
│                                                                   │
│   type ProgressEvent { Kind, Tool, Message, Elapsed }             │
│                                                                   │
│   processOptions {                                                │
│     …existing fields…                                             │
│     ProgressCallback func(ProgressEvent)  ← tool boundaries       │
│     StreamCallback   func(token string)   ← direct-mode tokens    │
│   }                                                               │
│                                                                   │
│   ProcessDirectSingleTurnStream(ctx, content, key, onToken)       │
│       └─→ runAgentLoop(opts.StreamCallback = onToken)             │
│                                                                   │
│   ProcessDirectWithProgress(ctx, content, key, onProgress)        │
│       └─→ runAgentLoop(opts.ProgressCallback = onProgress)        │
│                                                                   │
│   runLLMIteration():                                              │
│     if Direct && StreamCallback && Streamable provider:           │
│       provider.ChatStream(..., StreamCallback)                    │
│     else:                                                          │
│       provider.Chat(...)                                          │
│                                                                   │
│     for each tool call:                                           │
│       ProgressCallback({Kind: "tool_start",  Tool, Message})      │
│       result := tool.Execute(...)                                 │
│       ProgressCallback({Kind: "tool_done",   Tool, Elapsed})      │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ pkg/providers/types.go                                            │
│                                                                   │
│   type Streamable interface {                                     │
│       ChatStream(ctx, messages, model, options,                   │
│                  onToken func(string)) (*LLMResponse, error)      │
│   }                                                               │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ pkg/providers/llamacli/provider.go                                │
│                                                                   │
│   (*Provider).ChatStream():                                       │
│     • exec.Command(llama-cli, … --grammar text-only-envelope)     │
│     • cmd.StdoutPipe(); cmd.Start()                               │
│     • read stdout byte-by-byte through a small state machine:    │
│       state 0: scan for `"text"` key                              │
│       state 1: scan past colon + whitespace, then opening quote   │
│       state 2: decode each character (handle \n, \t, \", etc.)    │
│                emit each to onToken as it arrives                 │
│       state 3: drained; subprocess will exit                      │
│     • cmd.Wait(); return assembled LLMResponse                    │
└──────────────────────────────────────────────────────────────────┘
```

The streaming path is opt-in at every level. If any layer rejects it — agentic mode in the loop, missing `Streamable` on the provider, multiple fallback candidates configured — the call falls back transparently to the existing buffered `Chat()` path.

---

## 3. The Five Features

### 3.1 Thinking Indicator

`cmd/qclaw/internal/agent/spinner.go` introduces a small Braille-frame spinner (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`) that ticks every 100 ms on stderr. Each tick:

1. Writes `\r\033[K` to clear the previous line in place.
2. Writes the current frame + label + elapsed time in whole seconds.

Stderr keeps the spinner separate from response output on stdout — pipelines like `qclaw direct -m "blink" > sketch.txt` capture only the response while the spinner stays visible on the terminal.

The spinner exposes four operations:
- `Clear()` — wipe the line without stopping (useful when interleaving with progress messages).
- `SetLabel(s)` — change the displayed text mid-flight (used to switch from "thinking" to "running arduino").
- `Stop()` — terminate the goroutine, wipe the line. Idempotent.
- `Elapsed()` — return time since `startSpinner`.

### 3.2 Typing Indicator

Telegram's typing indicator is already implemented (`StartTyping` in `pkg/channels/telegram/telegram.go`, automatically triggered from `pkg/channels/base.go:280`). This document captures CLI parity — the spinner above plays the same role for terminal sessions.

### 3.3 Tool-Call / Iteration Progress Messages

`processOptions` gains a `ProgressCallback func(ProgressEvent)` field. Inside `runLLMIteration`, every tool dispatch is bracketed:

```go
toolStart := time.Now()
opts.ProgressCallback(ProgressEvent{
    Kind:    "tool_start",
    Tool:    tc.Name,
    Message: fmt.Sprintf("Calling %s(%s)", tc.Name, argsPreview),
})

toolResult := agent.Tools.ExecuteWithContext(...)

opts.ProgressCallback(ProgressEvent{
    Kind:    "tool_done",  // or "tool_error" if Err != nil
    Tool:    tc.Name,
    Message: ...,
    Elapsed: time.Since(toolStart),
})
```

The CLI agentic command (`runAgenticTurn` in `helpers.go`) wires this into stderr:
- `tool_start` → clear spinner, print `🔧 Calling arduino({"action":"upload",…})`, retitle spinner to `Running arduino…`.
- `tool_done` → print `✓  arduino completed (28.3s)`, retitle spinner back to `QClaw is thinking…`.
- `tool_error` → print `✗  arduino failed: …`.

Callers that don't want progress (existing internal call sites, tests) pass `nil` and pay zero overhead — the `if opts.ProgressCallback != nil` guard is the only cost.

### 3.4 Elapsed Time Display

Two flavors:

- **In-flight:** the spinner shows running elapsed time updated every second (`%s (%s)` formatted with `time.Duration.Round(time.Second)`).
- **Post-turn:** every turn prints a final footer line — `  ⏱  4.2s` — using `.Round(100*1000*1000)` for one-decimal precision.

Per-tool elapsed times come through the `ProgressEvent.Elapsed` field — `runAgenticTurn` displays them as `✓  arduino completed (28.3s)`.

### 3.5 Token Streaming (Direct Path Only)

The hardest change. Three layers had to cooperate.

**Provider layer.** `llamacli.Provider.ChatStream()`:

```go
stdoutPipe, _ := cmd.StdoutPipe()
cmd.Start()

reader := bufio.NewReaderSize(stdoutPipe, 256)
state := 0  // 0=scanning, 1=after-key, 2=streaming, 3=done
keyTarget := []byte(`"text"`)
keyMatch := 0

for {
    b, err := reader.ReadByte()
    if err == io.EOF { break }
    fullStdout.WriteByte(b)
    switch state {
    case 0: // scan for "text" literal
        if b == keyTarget[keyMatch] { keyMatch++ }
        else if b == keyTarget[0]    { keyMatch = 1 }
        else                          { keyMatch = 0 }
        if keyMatch == len(keyTarget) { state = 1 }
    case 1: // skip ws/colon, await opening "
        if b == '"' { state = 2 }
    case 2: // streaming chars inside the string
        if b == '\\' { decode escape, emit onToken(decoded) }
        else if b == '"' { state = 3 }
        else { onToken(string(b)) }
    }
}
cmd.Wait()
```

Streaming engages only when the response envelope is `{"text":"…"}` — i.e., the no-tools direct path. Tools require the full envelope to identify name + arguments before dispatch, so the agentic loop continues to use buffered `Chat()`. If streaming parsing falls through unexpectedly (state never reaches 3, or no `"text"` key is found), the provider falls back to the existing `extractJSON()` + `parseEnvelope()` pipeline so the call still returns a valid response.

**Interface layer.** `pkg/providers/types.go` declares:

```go
type Streamable interface {
    ChatStream(
        ctx context.Context,
        messages []Message,
        model string,
        options map[string]any,
        onToken func(string),
    ) (*LLMResponse, error)
}
```

This is an _optional_ capability interface alongside `ThinkingCapable`. Providers that don't implement it (Anthropic, OpenAI, Claude CLI, etc.) are detected via type assertion and the loop falls back to `Chat()`.

**Agent-loop layer.** `runLLMIteration` decides per-iteration whether to stream:

```go
streamable, canStream := agent.Provider.(providers.Streamable)
useStream := opts.Direct &&
             opts.StreamCallback != nil &&
             canStream &&
             len(activeCandidates) <= 1

if useStream {
    return streamable.ChatStream(ctx, messages, activeModel, llmOpts, opts.StreamCallback)
}
return agent.Provider.Chat(...)
```

The `len(activeCandidates) <= 1` clause excludes streaming when the user has multiple model candidates configured — the fallback chain expects a single buffered call to compare error classifications, and adding streaming there would require a much larger refactor. For the Uno Q default config (one model, llamacli provider) streaming engages on every `qclaw direct` call.

**CLI layer.** `runDirectTurn`:

```go
spin := startSpinner("QClaw is thinking…")
var firstToken atomic.Bool

onToken := func(tok string) {
    if firstToken.CompareAndSwap(false, true) {
        spin.Stop()
        fmt.Print("\nQClaw (direct): ")
    }
    fmt.Print(tok)
}

response, err := agentLoop.ProcessDirectSingleTurnStream(ctx, input, sessionKey, onToken)
```

The atomic flag guarantees the spinner stops exactly once, the label is re-printed exactly once, and races between the first token's render and the parent goroutine's spinner control are impossible.

---

## 4. What the User Sees

### Direct mode
```
You: which pins do PWM?
⠹ QClaw is thinking… (3s)            ← live spinner, ticks every 100 ms
QClaw (direct): The Uno Q exposes PWM on pins D3, D5, D6, D9, D10, D11…
                                       ↑ tokens arrive live as model decodes
  ⏱  4.2s                              ← final turn footer
```

### Agentic mode
```
You: Use the arduino tool to upload a blink sketch for D9.
⠴ QClaw is thinking… (8s)
  🔧 Calling arduino({"action":"upload","sketch":"…"})
⠦ Running arduino… (32s)               ← spinner label changes during tool
  ✓  arduino completed (28.3s)
QClaw: The sketch has been compiled and flashed to the board.
  ⏱  41.7s
```

### Telegram
The `StartTyping` action keeps the "typing…" indicator alive (re-fired every 4 s, since Telegram expires it after ~5 s) until the response arrives. Placeholder "Thinking… 💭" message is edited into the final reply. No change in this commit; documented for completeness.

---

## 5. Performance and Correctness Notes

**Zero overhead for non-streaming callers.** Every new field is opt-in with `nil` checks. The agent loop adds one type assertion and one boolean check per LLM call when streaming is requested; everything else is unchanged.

**Streaming does not change the final response.** `ChatStream` always assembles the full string and returns the same `LLMResponse` shape `Chat` would return. The session-save path in `runAgentLoop` is unchanged. Tests pass on `pkg/providers/llamacli`, `pkg/agent`, and `cmd/qclaw/internal/agent`.

**Subprocess timing.** Streaming does not reduce total walltime — the model still decodes at ~8 t/s. What it changes is _perceived_ latency: the user sees the first token after the model's prefill completes (~3 s warm cache) instead of after generation completes (~10 s for a 64-token response). For an 8 t/s decoder the user experiences each token as it lands.

**Fallback chains and streaming.** When the user has configured multiple fallback model candidates, streaming is disabled to preserve fallback semantics. This is the right tradeoff for now: the Uno Q track ships one model by default, and the fallback chain is mostly a cloud-providers concern.

**The spinner is stderr-only.** Pipes and redirects (`qclaw direct -m "blink" > out.txt`) capture only the response. The spinner remains visible on the TTY but doesn't contaminate captured output.

---

## 6. File Inventory

| File | Lines added | Purpose |
|---|---|---|
| `pkg/providers/types.go` | +15 | `Streamable` interface |
| `pkg/providers/llamacli/provider.go` | +179 | `ChatStream` method + incremental envelope parser |
| `pkg/agent/loop.go` | +120 | `ProgressEvent`, `ProgressCallback`, `StreamCallback`, `ProcessDirectSingleTurnStream`, `ProcessDirectWithProgress`, streaming branch in iteration loop, tool-progress emissions |
| `cmd/qclaw/internal/agent/spinner.go` | +96 (new) | Braille spinner with elapsed-time display |
| `cmd/qclaw/internal/agent/direct.go` | +42 | `runDirectTurn` — spinner + streaming wiring |
| `cmd/qclaw/internal/agent/helpers.go` | +30 | `runAgenticTurn` — spinner + tool-progress wiring |
| **Total** | **+463 / −33** | |

Commit: `966abfa` on branch `QClaw-v2`.
