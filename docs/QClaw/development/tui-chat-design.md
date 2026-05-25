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

### Direct mode (raw `llama-server` chat)

A long-lived `http.Client` POSTs each submitted message to `http://127.0.0.1:8083/v1/chat/completions` with `"stream": true`. A goroutine reads the SSE stream line-by-line, decodes each `choices[0].delta.content` chunk, and appends it to the output pane through `app.QueueUpdateDraw()`.

- True token streaming, indistinguishable from `llama-cli -cnv` in feel.
- Conversation history is kept as a `[]openai.ChatMessage` slice; each submit appends the new user turn and re-sends the full history.
- The system prompt is the same `SOUL.md` + `IDENTITY.md` bundle the agentic path uses, so model behavior matches.

### Agentic mode (full agent loop)

Spawn `qclaw agent` once as a child process with piped `stdin`/`stdout`/`stderr`. A goroutine pumps the agent's stdout into the output pane (line-buffered — the agent emits chunks of formatted output, not raw tokens). The input field writes the user's line + `\n` to stdin. The subprocess stays alive across messages until the user exits the chat page.

- Full agentic capability: 8 tools, pre-router, 15 skills, multi-iteration loop.
- Output is *not* a clean token stream — it's the agent's terminal output, including tool-call markup, reasoning blocks, and bulk text dumps. This is a fundamental limitation of the current agent: it accumulates the full LLM response before printing. Fixing it would require streaming hooks inside `pkg/agent/loop.go`.

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

No changes needed to `pkg/agent`, `pkg/providers`, or any other production code path. The TUI uses existing public APIs only.

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
