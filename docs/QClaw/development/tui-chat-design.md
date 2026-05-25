# TUI In-App Chat — Design Proposal

A design proposal for adding an interactive chat surface to `cmd/qclaw-launcher-tui` so users can test both the **Direct** (raw model) and **Agentic** (full agent loop) paths without ever leaving the TUI. Today the TUI's `Start Talk` action suspends the TUI and drops into `qclaw agent` in the host terminal; this proposal replaces that with an in-TUI chat page that supports both modes and live token streaming.

**Status:** proposal — not yet implemented.

---

## Goals

1. Add a `Chat` page to the TUI that hosts an interactive conversation with the model.
2. Support two modes selectable at runtime, with no TUI suspension:
   - **Direct** — raw chat against the `llama-server` HTTP API, with true token-by-token streaming (same UX as `llama-cli -cnv`).
   - **Agentic** — full QClaw agent loop, including tools, the 23-rule pre-router, and the 15-skill tree.
3. Let the user flip between modes (F2) inside the same chat page without restarting anything.
4. Keep the existing `Start Gateway` and `Start Talk` actions working for users who prefer the terminal-based workflow.

---

## Layout

```
┌─ Chat ─────────────────────────────────────┐
│ Mode: [● Direct] [○ Agentic]  Engine: yzma │
├────────────────────────────────────────────┤
│ You: which pins do PWM?                    │
│                                            │
│ QClaw: D3, D5, D6, D9, D10, D11▎          │  ← streaming
│                                            │
├────────────────────────────────────────────┤
│ > _                                        │
└────────────────────────────────────────────┘
 F2 toggle mode · Ctrl+L clear · ESC back
```

- **Header strip** — current mode indicator + engine name (read from `agents.defaults.model_name`).
- **Output pane** — `tview.TextView` with scrollback, word wrap, dynamic colors. Updates from background goroutines flushed via `app.QueueUpdateDraw()`.
- **Input field** — `tview.InputField`. Enter submits, Ctrl+L clears the output pane, Esc returns to the main menu.
- **Footer** — keybinding hints.

---

## How each mode works

### Direct mode

Direct mode targets QClaw's real Direct path — a single LLM call with the **23-rule pre-router** applied before submission. The pre-router (`pkg/agent/skill_preload.go`) matches the user's query against 23 routing rules and inlines relevant skill content directly into the system prompt. This is what gives QClaw Direct mode its targeted, context-rich responses.

**Important:** a naïve implementation that POSTs directly to `/v1/chat/completions` bypasses `pkg/agent` entirely and therefore bypasses the pre-router. That produces raw model output with no skill context — indistinguishable from `llama-cli -cnv` in behavior, not QClaw. See *Pre-router and the Direct path* below for the three implementation options.

**Intended behavior (Option 3 — recommended):**

A long-lived `http.Client` POSTs each submitted message to `http://127.0.0.1:8083/v1/chat/completions` with `"stream": true`, but only after the pre-router has run and enriched the system prompt. A goroutine reads the SSE stream line-by-line, decodes each `choices[0].delta.content` chunk, and appends it to the output pane through `app.QueueUpdateDraw()`.

- True token streaming, pre-router applied — the combination that makes Direct mode in the TUI equivalent to `qclaw direct`.
- Conversation history is kept as a `[]openai.ChatMessage` slice; each submit appends the new user turn and re-sends the full history.
- Requires adding streaming hooks to `ProcessDirectSingleTurn` in `pkg/agent/loop.go` (~150 lines across `pkg/agent` and `pkg/providers`). See *Pre-router and the Direct path* for scope.

### Agentic mode (full agent loop)

Spawn `qclaw agent` once as a child process with piped `stdin`/`stdout`/`stderr`. A goroutine pumps the agent's stdout into the output pane (line-buffered — the agent emits chunks of formatted output, not raw tokens). The input field writes the user's line + `\n` to stdin. The subprocess stays alive across messages until the user exits the chat page.

- Full agentic capability: 8 tools, pre-router, 15 skills, multi-iteration loop.
- Output is *not* a clean token stream — it's the agent's terminal output, including tool-call markup, reasoning blocks, and bulk text dumps. This is a fundamental limitation of the current agent: it accumulates the full LLM response before printing. Fixing it would require streaming hooks inside `pkg/agent/loop.go`.

---

## Pre-router and the Direct path

QClaw's "Direct" path is not raw model chat — it is `ProcessDirectSingleTurn` in `pkg/agent/loop.go`, which applies the 23-rule pre-router (`pkg/agent/skill_preload.go`) before each LLM call. The pre-router inspects the user's message, matches it against routing rules, and inlines matching skill content into the system prompt. Without it, the model has no awareness of QClaw's skills, tools, or domain knowledge.

Raw `/v1/chat/completions` chat bypasses `pkg/agent` entirely. The three implementation options for TUI Direct mode are:

| Option | Pre-router | Token streaming | Implementation scope |
|---|---|---|---|
| **1 — Raw chat** | ✗ | ✓ | TUI-only, no pkg changes. Not true QClaw Direct. |
| **2 — `qclaw direct` subprocess** | ✓ | ✗ (bulk output) | Same as Agentic mode's subprocess pattern; no streaming. |
| **3 — Streaming hooks in `ProcessDirectSingleTurn`** ⭐ | ✓ | ✓ | ~150 LoC across `pkg/agent/loop.go` and `pkg/providers`; the right fix. |

**Recommendation: Option 3.** Add an optional streaming callback to `ProcessDirectSingleTurn` (and to the underlying provider's `Chat()` call path). The TUI passes a callback that writes each token to the output pane via `app.QueueUpdateDraw()`. This is the only option that delivers both the pre-router and token-by-token streaming — the two qualities that define QClaw Direct mode.

Until Option 3 is implemented, the TUI can ship with Option 1 as a clearly-labelled "Raw chat (no pre-router)" mode — useful for baseline testing — while Option 3 remains an open implementation task. This should be documented in the UI header strip so users understand which mode is active.

---

## Design decisions

### 1. Llama-server lifecycle

Direct mode needs `llama-server` listening on port 8083. Agentic mode's provider also auto-spawns one on the same port (see `pkg/providers/llamaserver`). The TUI must decide who owns the process so the two modes don't race.

**Decision:** the TUI owns it. On chat-page entry, the TUI spawns `engines/yzma/lib/llama-server` (the same argv the provider would build) if no process is already listening on 8083. On chat-page exit, the TUI kills it. Agentic mode detects the existing port and reuses it via the provider's standard health-check path — no double-spawn.

Trade-off: the first entry into chat-mode pays the full 3–5 min cold load before either mode is usable. We display "Loading model… (cold start, 3–5 min)" in the output pane while `/health` returns non-OK, then unlock the input field.

### 2. Mode switching resets history

Direct and Agentic operate on fundamentally different context shapes:
- Direct: `[]openai.ChatMessage` with raw user/assistant turns.
- Agentic: a working session managed by `pkg/agent`, including tool call/result pairs, pre-router injections, and iteration state.

Replaying one as the other produces nonsense. **Decision:** toggling F2 clears the output pane and starts a fresh conversation in the new mode. The agent subprocess stays running across toggles so the switch is instant.

### 3. Menu placement

**Decision:** replace `Start Talk` with a single `Chat` entry that opens the new page. `Start Talk` exists today only because the TUI couldn't host an interactive chat — once it can, the suspend-and-launch dance is strictly worse than an in-TUI chat page.

`Start Gateway` stays. It's about wiring up channel adapters (Telegram, Discord, etc.) for remote conversation, not about local testing.

### 4. Mutual exclusion with gateway

The gateway also wants port 8083. **Decision:** disable the `Chat` menu item while the gateway is running, and disable `Start Gateway` while the chat page is open. Enforced by checking `s.isGatewayRunning()` before either action.

---

## Implementation plan

| File | Change | Approx. LoC |
|---|---|---|
| `cmd/qclaw-launcher-tui/internal/ui/chat.go` | New file — chat page, both modes, mode toggle, lifecycle | ~400 |
| `cmd/qclaw-launcher-tui/internal/ui/app.go` | Replace `Start Talk` menu entry with `Chat`; add `s.openChat()`; add gateway/chat mutual-exclusion checks | ~30 |
| `cmd/qclaw-launcher-tui/internal/ui/style.go` | Add 1–2 colors for streaming cursor + mode indicator | ~5 |

**If shipping Option 3 (recommended)** — additional changes required before the TUI work above:

| File | Change | Approx. LoC |
|---|---|---|
| `pkg/agent/loop.go` | Add `StreamFunc func(token string)` parameter to `ProcessDirectSingleTurn`; pass it through to the provider call | ~40 |
| `pkg/providers/llamaserver/provider.go` | Add streaming variant of `Chat()` that accepts a token callback; reuse the existing SSE-reading logic | ~80 |
| `pkg/providers/openai_compat/client.go` | Expose SSE stream reader as a first-class method (currently private to the HTTP layer) | ~30 |

These changes add streaming to the production code path — unit-testable independently of the TUI. The TUI `chat.go` then calls the streaming variant via the existing provider interface rather than reaching directly to the HTTP layer.

### Streaming-token pseudocode (Direct mode)

```go
func (c *chatPage) sendDirect(prompt string) {
    c.history = append(c.history, openai.ChatMessage{Role: "user", Content: prompt})
    body, _ := json.Marshal(map[string]any{
        "model":    c.engineName,
        "messages": c.history,
        "stream":   true,
    })
    req, _ := http.NewRequest("POST", c.endpoint+"/v1/chat/completions", bytes.NewReader(body))
    req.Header.Set("Content-Type", "application/json")
    resp, _ := c.httpClient.Do(req)
    defer resp.Body.Close()

    scanner := bufio.NewScanner(resp.Body)
    var assistant strings.Builder
    for scanner.Scan() {
        line := scanner.Text()
        if !strings.HasPrefix(line, "data: ") { continue }
        payload := strings.TrimPrefix(line, "data: ")
        if payload == "[DONE]" { break }
        var chunk struct {
            Choices []struct{ Delta struct{ Content string } }
        }
        if json.Unmarshal([]byte(payload), &chunk) != nil { continue }
        if len(chunk.Choices) == 0 { continue }
        tok := chunk.Choices[0].Delta.Content
        assistant.WriteString(tok)
        c.app.QueueUpdateDraw(func() { c.output.Write([]byte(tok)) })
    }
    c.history = append(c.history, openai.ChatMessage{Role: "assistant", Content: assistant.String()})
}
```

### Subprocess pump pseudocode (Agentic mode)

```go
func (c *chatPage) startAgent() error {
    cmd := exec.Command("qclaw", "agent")
    stdin, _ := cmd.StdinPipe()
    stdout, _ := cmd.StdoutPipe()
    if err := cmd.Start(); err != nil { return err }
    c.agentCmd, c.agentStdin = cmd, stdin
    go func() {
        scanner := bufio.NewScanner(stdout)
        for scanner.Scan() {
            line := scanner.Text() + "\n"
            c.app.QueueUpdateDraw(func() { c.output.Write([]byte(line)) })
        }
    }()
    return nil
}

func (c *chatPage) sendAgentic(prompt string) {
    fmt.Fprintln(c.agentStdin, prompt)
}
```

---

## Open questions

1. **Cursor "▎" character during streaming**: simple to add — write `"▎"` after each token, then erase it before writing the next. Worth doing for the live feel.
2. **Token count / TPS display** in the header during streaming? Easy stretch goal once Direct mode is wired up.
3. **Persist chat history** between TUI invocations? Out of scope for v1 — the existing gateway sessions at `~/.qclaw/workspace/sessions/` already cover this for the agentic side.
4. **Color the assistant output** differently from the user input? Strong yes — `tview.TextView` supports inline color tags.

---

## Related

- `cmd/qclaw-launcher-tui/internal/ui/app.go` — current `Start Talk` and `Start Gateway` actions.
- `pkg/providers/llamaserver/provider.go` — the auto-spawn logic that the TUI's Direct-mode lifecycle should mirror.
- `pkg/agent/loop.go` — `ProcessDirectSingleTurn` and the agent loop; the place to add token-level streaming hooks if Agentic mode ever needs live tokens.
- [`engines/yzma/lib/BUILD.md`](../../../engines/yzma/lib/BUILD.md) — `llama-server` HTTP API reference, including the `/v1/chat/completions` streaming contract.
