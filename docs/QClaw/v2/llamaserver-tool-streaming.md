# QClaw v2: Tool-Aware Streaming on llamaserver + Richer Progress Events

This document records the agentic streaming improvements added in commit `7229af2`. Before this change, the agentic path was entirely buffered: the CLI spun while the agent loop completed every tool-call cycle silently, then printed the model's full answer as one block. The changes below extend live token delivery to the agentic path and give the CLI complete visibility into the model's multi-step reasoning trail.

---

## 1. The Problem

The previous round of UX improvements (commit `966abfa`, `docs/QClaw/v2/cli-ux-improvements.md`) established:

- A Braille spinner with elapsed-time display on stderr.
- Tool-progress callbacks (`tool_start` / `tool_done` / `tool_error`) at every tool boundary.
- Token streaming for the **direct path** only (`qclaw direct`).

Three gaps remained:

| Gap | Symptom |
|---|---|
| No streaming in agentic mode | The model's final answer appeared in one block after all tool calls finished |
| Truncated tool arguments | Progress messages showed `Calling tool(…)` — a placeholder, not actual arguments |
| No iteration visibility | Multi-step tool chains showed repeated `"QClaw is thinking…"` with no step count |

The root cause for the streaming gap was architectural: `Streamable.ChatStream` did not accept a `tools` parameter, so the agent loop could not stream turns that carried tool definitions — which in agentic mode is every turn.

The truncated-args and iteration gaps were simple omissions in `ProgressEvent` and the loop's emission code.

---

## 2. Architecture

### 2.1 `ErrStreamingUnsupported` Sentinel

Providers that can stream text-only (like llamacli) need a way to signal "I cannot stream this particular call" without making the agent loop aware of provider internals. The sentinel lives in the leaf package `pkg/providers/protocoltypes/errors.go` to avoid an import cycle:

```go
// pkg/providers/protocoltypes/errors.go
package protocoltypes

import "errors"

var ErrStreamingUnsupported = errors.New("streaming not supported for this configuration")
```

`pkg/providers/types.go` re-exports it so callers import only the parent package:

```go
var ErrStreamingUnsupported = protocoltypes.ErrStreamingUnsupported
```

The agent loop checks for it explicitly:

```go
resp, sErr := streamable.ChatStream(ctx, messages, providerToolDefs, activeModel, llmOpts, opts.StreamCallback)
if !errors.Is(sErr, providers.ErrStreamingUnsupported) {
    return resp, sErr
}
// fall through to buffered Chat()
```

Any other error aborts the call normally. `ErrStreamingUnsupported` is the single agreed signal that streaming declined gracefully.

### 2.2 `Streamable` Interface Extension

`ChatStream` gains a `tools []ToolDefinition` parameter:

```go
// pkg/providers/types.go
type Streamable interface {
    ChatStream(
        ctx context.Context,
        messages []Message,
        tools []ToolDefinition,
        model string,
        options map[string]any,
        onToken func(string),
    ) (*LLMResponse, error)
}
```

This lets the provider see whether the call is tool-bearing and decide how to handle it — either implement tool_calls delta parsing (llamaserver) or return `ErrStreamingUnsupported` (llamacli).

### 2.3 llamaserver: SSE Tool-Calls Delta Parser

`llamaserver.Provider.ChatStream()` posts a streaming `/v1/chat/completions` request with `"stream": true` and, when tools are present, `"tool_choice": "auto"`. The SSE response carries two interleaved event streams:

- `choices[0].delta.content` — text tokens arriving as the model decodes.
- `choices[0].delta.tool_calls[{index, id, function:{name, arguments}}]` — tool-call fragments, where the `arguments` field arrives piecemeal across many delta chunks and must be concatenated per index.

The parser accumulates both:

```
type tcAccum struct {
    id        string
    typ       string
    name      string
    arguments strings.Builder   // concatenate across delta chunks
}

toolAccs := map[int]*tcAccum{}  // keyed by delta.index

for each SSE line "data: {...}":
    content delta → contentSB.WriteString(tok); onToken(tok)
    tool_calls delta → toolAccs[index].{id,typ,name,arguments} += delta fields

when [DONE] arrives:
    sort toolAccs by index (deterministic dispatch order)
    build ToolCall slice from accumulated fields
    return LLMResponse{Content, FinishReason, ToolCalls}
```

Text tokens stream to the user immediately. Tool-call fields stay buffered until the stream is complete so the agent loop receives them as a unit and can dispatch without a race on partial arguments. The assembled `LLMResponse` is identical in shape to what `Chat()` would have returned.

The SSE scanner uses a 1 MiB buffer (`scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)`) because individual tool_calls delta lines with long argument payloads can exceed the default 64 KiB bufio limit.

### 2.4 llamacli: Graceful Decline

llamacli's `ChatStream` gets one new guard at the top:

```go
func (p *Provider) ChatStream(..., tools []ToolDefinition, ...) (*LLMResponse, error) {
    if len(tools) > 0 {
        return nil, protocoltypes.ErrStreamingUnsupported
    }
    // existing text-only streaming
}
```

When the agent loop passes tools (every agentic turn), llamacli declines and the loop falls back to `Chat()`. Text-only streaming (no tools) is preserved.

### 2.5 Agent Loop Gate Change

Previously, streaming was guarded by `opts.Direct`:

```go
useStream := opts.Direct && opts.StreamCallback != nil && canStream && len(activeCandidates) <= 1
```

That gate is removed. Any call with `StreamCallback` set may attempt streaming; provider capability and `ErrStreamingUnsupported` are the only arbiters:

```go
useStream := opts.StreamCallback != nil && canStream && len(activeCandidates) <= 1

callLLM := func() (*providers.LLMResponse, error) {
    if useStream {
        resp, sErr := streamable.ChatStream(ctx, messages, providerToolDefs, activeModel, llmOpts, opts.StreamCallback)
        if !errors.Is(sErr, providers.ErrStreamingUnsupported) {
            return resp, sErr
        }
    }
    return agent.Provider.Chat(ctx, messages, providerToolDefs, activeModel, llmOpts)
}
```

### 2.6 Richer `ProgressEvent`

`ProgressEvent` gains two new fields:

```go
type ProgressEvent struct {
    Kind      string        // "iteration" | "tool_start" | "tool_done" | "tool_error"
    Tool      string
    Message   string
    Elapsed   time.Duration
    Arguments string        // NEW: verbatim JSON arguments string
    Iteration int           // NEW: 1-based loop turn counter
}
```

**Iteration events.** At the top of every agent loop turn the loop emits:

```go
opts.ProgressCallback(ProgressEvent{Kind: "iteration", Iteration: iteration})
```

This lets the CLI retitle the spinner with the current step count without printing a line.

**Full arguments.** `tool_start` events now carry the complete JSON arguments string instead of a truncated preview:

```go
opts.ProgressCallback(ProgressEvent{
    Kind:      "tool_start",
    Tool:      tc.Name,
    Arguments: tc.Arguments,  // full JSON, not "…"
    Iteration: iteration,
    Message:   fmt.Sprintf("%s(%s)", tc.Name, tc.Arguments),
})
```

### 2.7 `ProcessAgenticWithProgressStream`

A new entry point on `AgentLoop` accepts both callbacks at once:

```go
func (a *AgentLoop) ProcessAgenticWithProgressStream(
    ctx context.Context,
    content, sessionKey string,
    onProgress func(ProgressEvent),
    onToken func(string),
) (string, error)
```

`ProcessDirectWithProgress` is updated to delegate here with `onToken = nil`, keeping the existing direct-path call sites unchanged.

### 2.8 CLI Wiring

`cmd/qclaw/internal/agent/helpers.go:runAgenticTurn` wires both callbacks:

```go
spin := startSpinner("QClaw is thinking…")
var firstToken atomic.Bool

progress := func(ev agent.ProgressEvent) {
    spin.Clear()
    switch ev.Kind {
    case "iteration":
        if ev.Iteration > 1 {
            spin.SetLabel(fmt.Sprintf("QClaw is thinking (step %d)…", ev.Iteration))
        }
    case "tool_start":
        fmt.Fprintf(os.Stderr, "  🔧 [iter %d] %s(%s)\n", ev.Iteration, ev.Tool, ev.Arguments)
        spin.SetLabel(fmt.Sprintf("Running %s…", ev.Tool))
    case "tool_done":
        fmt.Fprintf(os.Stderr, "  ✓  %s (%s)\n", ev.Message, ev.Elapsed.Round(100*1000*1000))
        spin.SetLabel("QClaw is thinking…")
    case "tool_error":
        fmt.Fprintf(os.Stderr, "  ✗  %s (%s)\n", ev.Message, ev.Elapsed.Round(100*1000*1000))
        spin.SetLabel("QClaw is thinking…")
    }
}

onToken := func(tok string) {
    if firstToken.CompareAndSwap(false, true) {
        spin.Stop()
        fmt.Print("\nQClaw: ")
    }
    fmt.Print(tok)
}

response, err := agentLoop.ProcessAgenticWithProgressStream(ctx, input, sessionKey, progress, onToken)
elapsed := spin.Elapsed()
spin.Stop()

// If streaming never engaged (provider fallback or tool-only turn), print buffered response.
if !firstToken.Load() {
    fmt.Printf("\nQClaw: %s", response)
}
fmt.Printf("\n  ⏱  %s\n\n", elapsed.Round(100*1000*1000))
```

The `firstToken` atomic flag prevents the `QClaw: ` prefix from printing twice if streaming did engage, and guarantees the buffered response still prints if the provider returned `ErrStreamingUnsupported` or emitted only tool calls with no final text content.

---

## 3. What the User Sees

### Single-turn agentic with llamaserver (streaming)

```
You: What are the specs of this board?

⠹ QClaw is thinking… (1s)
QClaw: The Arduino Uno Q is powered by a Qualcomm QRB2210 SoC — four Cortex-A53
cores at up to 2.0 GHz, 4 GB LPDDR4X, and an Adreno 702 GPU with OpenCL 2.0 …
                ↑ tokens arrive live as the model decodes

  ⏱  3.8s
```

### Multi-step agentic with llamaserver (tools + streaming final turn)

```
You: Flash a blink sketch to D9, then confirm the board is healthy.

⠙ QClaw is thinking… (2s)
  🔧 [iter 1] arduino({"action":"upload","sketch":"void setup(){pinMode(9,OUTPUT);}void loop(){digitalWrite(9,HIGH);delay(500);digitalWrite(9,LOW);delay(500);}","board":"uno_q"})
⠴ Running arduino… (28s)
  ✓  arduino: upload ok (27.6s)
⠦ QClaw is thinking (step 2)… (3s)
  🔧 [iter 2] arduino({"action":"status"})
⠧ Running arduino… (2s)
  ✓  arduino: status ok (1.9s)
⠇ QClaw is thinking (step 3)… (1s)
QClaw: Done! The blink sketch is running on D9 and the board reports healthy —
voltage 3.28 V, temperature 41 °C, no fault flags.

  ⏱  38.4s
```

### Agentic with llamacli (tool-calls, no final-turn streaming)

llamacli returns `ErrStreamingUnsupported` for tool-bearing calls. The loop falls back to `Chat()`, the final response is buffered, and `firstToken` never fires — so the CLI prints the full response after the spinner stops. The progress messages and iteration counter still appear exactly as above.

```
You: Use the arduino tool to read the ADC on A0.

⠹ QClaw is thinking… (2s)
  🔧 [iter 1] arduino({"action":"adc_read","pin":"A0"})
⠼ Running arduino… (1s)
  ✓  arduino: read ok (0.8s)

QClaw: The ADC on A0 reads 1023 (5.00 V reference, 3.3 V on pin).

  ⏱  4.1s
```

---

## 4. Correctness and Fallback Notes

**Streaming does not alter the assembled response.** `ChatStream` always returns an `LLMResponse` with the same `Content`, `FinishReason`, and `ToolCalls` fields that `Chat()` would have returned. The session-save and history-append paths in the agent loop are unchanged.

**Tool-calls-only turns.** When the model emits only tool_calls (no text content in the final turn), `onToken` is never called, `firstToken` stays false, and the CLI prints the buffered response. This is the correct behavior — the model produced no text to stream.

**Multiple model candidates.** The `len(activeCandidates) <= 1` guard from commit `966abfa` remains, disabling streaming when a fallback chain is configured. Tool-aware streaming adds no new restrictions here.

**llamaserver process restart.** `ensureServer` is called at the top of both `Chat()` and `ChatStream()`, so a crashed llama-server process is detected and restarted before either path proceeds.

**Import cycle prevention.** `ErrStreamingUnsupported` lives in `pkg/providers/protocoltypes` — a leaf package with no upward imports. Both `pkg/providers/llamacli` and `pkg/providers/llamaserver` import it directly; `pkg/providers/types.go` re-exports it. No package in the providers tree imports its own parent.

---

## 5. File Inventory

| File | Changes | Purpose |
|---|---|---|
| `pkg/providers/protocoltypes/errors.go` | +10 (new file) | `ErrStreamingUnsupported` sentinel in leaf package |
| `pkg/providers/types.go` | +12 / −1 | `Streamable.ChatStream` gains `tools` param; re-exports sentinel |
| `pkg/providers/llamaserver/provider.go` | +188 | Full `ChatStream` with SSE tool_calls delta parser |
| `pkg/providers/llamacli/provider.go` | +12 / −1 | `ChatStream` updated signature; early return when tools present |
| `pkg/agent/loop.go` | +81 / −14 | `ProgressEvent.{Arguments,Iteration}`; iteration event emission; streaming gate change; `ProcessAgenticWithProgressStream` |
| `cmd/qclaw/internal/agent/helpers.go` | +37 / −1 | `runAgenticTurn` wires `progress` + `onToken`; calls `ProcessAgenticWithProgressStream` |
| **Total** | **+340 / −17** | |

Commit: `7229af2` on branch `QClaw-v2`.
