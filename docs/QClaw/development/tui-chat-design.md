# TUI In-App Chat

An interactive chat surface inside `cmd/qclaw-launcher-tui` that lets users test both the **Direct** (pre-router + single LLM call, token streaming) and **Agentic** (full agent loop, tools, streaming) paths without ever leaving the TUI. The previous `Start Talk` action suspended the TUI and dropped into `qclaw agent` in the host terminal; this page replaces it.

**Status:** implemented — `QClaw-v2` branch, commit `740bfa5`.

---

## Goals

1. Add a `Chat` page to the TUI hosting an interactive conversation with the model.
2. Support two modes selectable at runtime, with no TUI suspension:
   - **Direct** — pre-router + single LLM call, true token-by-token streaming.
   - **Agentic** — full QClaw agent loop: tools, 23-rule pre-router, 15-skill tree, multi-iteration, streaming.
3. Let the user flip between modes (F2) inside the same chat page without restarting anything.
4. Replace `Start Talk` with `Chat`; keep `Start Gateway` unchanged.

---

## Layout

```
┌─ Chat ──────────────────────────────────────────────────────────┐
│ ● Direct  ○ Agentic  │  yzma  │  F2:mode  Ctrl+L:clear  Esc:back│
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ You: which pins do PWM?                                          │
│ QClaw: D3, D5, D6, D9, D10, D11▎         ← streaming tokens     │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│ ┌─ Message ──────────────────────────────────────────────────── │
│ │You: _                                                          │
│ └────────────────────────────────────────────────────────────── │
└─────────────────────────────────────────────────────────────────┘
```

- **Mode bar** (1 row) — active mode shown with green `●`; engine name from `agents.defaults.model`; keybinding hints. Background uses `MoreContrastBackgroundColor`.
- **Output pane** — `tview.TextView`, `SetDynamicColors(true)`, `SetWordWrap(true)`, `SetScrollable(true)`. All goroutine updates go through `app.QueueUpdateDraw()`.
- **Input field** — `tview.InputField` with label `"You: "`. Enter submits; placeholder becomes `⊙ thinking…` while a request is in-flight. Esc closes the page.
- **Color scheme** (inline tview tags, not constants):
  - `[#8be9fd]` — user turns
  - `[#f1faff]` — assistant turns
  - `[#bd93f9]` — tool calls / engine name
  - `[#50fa7b]` — active mode indicator / tool-done
  - `[#ff5555]` — errors / tool-error

---

## How each mode works

### Direct mode

Calls `agentLoop.ProcessDirectSingleTurnStream(ctx, text, sessionKey, onToken)`.

The pre-router (`pkg/agent/skill_preload.go`) runs before the LLM call, inlining skill content into the system prompt. The underlying `llamaserver.Provider.ChatStream` reads the SSE stream and calls `onToken` for each `choices[0].delta.content` delta. Each callback queues a `QueueUpdateDraw` to append the token to the output pane.

Session history is managed by the agent loop's session store (file-backed at `~/.qclaw/workspace/sessions/`). The session key `"tui:direct:N"` where N is the toggle counter means each mode switch starts a clean session.

If the active provider does not implement `providers.Streamable`, the loop falls back to buffered `Chat()` transparently and the full response is written at completion.

### Agentic mode

Calls `agentLoop.ProcessAgenticWithProgressStream(ctx, text, sessionKey, onProgress, onToken)`.

The full tool loop runs (up to `max_tool_iterations`). An `onProgress` callback renders tool events inline in the output pane:
- `[#bd93f9]⚙ toolName(args)[-]` on `tool_start`
- `[#50fa7b]✓ message[-]` on `tool_done`
- `[#ff5555]✗ message[-]` on `tool_error`

An `onToken` callback streams the model's final text turn. If the provider's streaming path refuses tool-aware requests (`ErrStreamingUnsupported`), the loop falls back to buffered mode silently.

Session key is `"tui:agentic:N"`.

---

## Pre-router and the Direct path

QClaw's "Direct" path is `ProcessDirectSingleTurnStream` in `pkg/agent/loop.go` — not raw `/v1/chat/completions` chat. The pre-router (`pkg/agent/skill_preload.go`) runs before each LLM call, matching the user query against 23 routing rules and inlining relevant skill content into the system prompt.

When this document was first written, the streaming infrastructure did not yet exist and three options were identified:

| Option | Pre-router | Token streaming | Status |
|---|---|---|---|
| **1 — Raw HTTP chat** | ✗ | ✓ | Not used — bypasses pkg/agent |
| **2 — `qclaw direct` subprocess** | ✓ | ✗ (bulk output) | Not used |
| **3 — Streaming hooks in `ProcessDirectSingleTurn`** ⭐ | ✓ | ✓ | **Implemented** |

Option 3 was already fully implemented in the codebase before the TUI work began:
- `ProcessDirectSingleTurnStream` with `onToken func(string)` existed in `pkg/agent/loop.go`
- `llamaserver.Provider` already implemented `providers.Streamable` via `ChatStream`
- The agent's `runLLMIteration` already detected `Streamable` and routed to it when `StreamCallback != nil`

The TUI consumes this existing API directly — no changes to `pkg/agent` or `pkg/providers` were needed.

---

## Design decisions

### 1. Llama-server lifecycle

**Decision:** the `AgentLoop`'s provider (`llamaserver.Provider`) owns the llama-server process. The chat page creates a fresh `AgentLoop` (and therefore a fresh provider) on page entry via `newChatPage()`. The provider's `ensureServer()` spawns `llama-server` on the first `Chat()` or `ChatStream()` call and keeps it running for the lifetime of the page.

The cold start (3–5 min on Uno Q) is deferred to the first submit. During the wait, the input placeholder shows `⊙ thinking…`. The `AgentLoop` and `MessageBus` are closed in a background goroutine when the page exits (ESC or context cancel) so the UI is never blocked.

Both Direct and Agentic mode share the same `AgentLoop` and therefore the same llama-server process — no double-spawn on mode switch.

### 2. Mode switching resets history

**Decision:** each mode toggle increments a `toggleCtr` counter. The session key is `"tui:direct:N"` / `"tui:agentic:N"` where N = `toggleCtr`. A new key starts a new session with empty history. The output pane is also cleared. The `AgentLoop` stays alive — only the session context resets.

### 3. Menu placement

**Decision:** `Start Talk` is replaced by `Chat`. `Start Talk` suspended the TUI; the in-TUI chat page is strictly better for local testing. `Start Gateway` is unchanged.

### 4. Mutual exclusion with gateway

**Decision:** `Chat` is disabled while the gateway is running (`s.isGatewayRunning()`); `Start Gateway` is disabled while the chat page is open (`s.isChatOpen`). Both checks live in `refreshMainMenu` in `app.go`. When the chat page closes, `isChatOpen` is set to `false` before `s.pop()` so the menu refreshes correctly.

---

## Implementation

| File | Change | Actual LoC |
|---|---|---|
| `cmd/qclaw-launcher-tui/internal/ui/chat.go` | New — `chatPage` struct, both modes, toggle, lifecycle | 327 |
| `cmd/qclaw-launcher-tui/internal/ui/app.go` | Replace `Start Talk` with `Chat`; `isChatOpen`; `openChat()`; mutual-exclusion | +35 / -19 |

`pkg/agent`, `pkg/providers`, and `style.go` were not modified — the TUI uses existing public APIs only.

### Key types and entry points

```
appState.isChatOpen bool                       // mutual-exclusion flag
appState.openChat()                            // validates model, creates chatPage, pushes page
chatPage.dispatch(text)                        // called on Enter; spawns goroutine
chatPage.runDirect(text, sessionKey)           // → ProcessDirectSingleTurnStream
chatPage.runAgentic(text, sessionKey)          // → ProcessAgenticWithProgressStream
chatPage.toggleMode()                          // F2 handler: bump toggleCtr, clear output
chatPage.close()                               // ESC: cancel ctx, close loop/bus, pop page
```

### Session key scheme

```
"tui:direct:0"   — first Direct session (initial page open)
"tui:agentic:1"  — after first F2 toggle to Agentic
"tui:direct:2"   — after second F2 toggle back to Direct
```

Each key maps to a distinct file in `~/.qclaw/workspace/sessions/`.

---

## Stretch goals (not yet implemented)

1. **Streaming cursor `▎`** — write `▎` after each token, erase before the next. Adds live feel.
2. **Token count / TPS display** in the mode bar during streaming. Easy once the provider exposes usage info from the SSE stream's final chunk.
3. **Persist chat history** across TUI invocations. The session files already exist on disk — a "resume" option on page entry could load the last session for each mode.

---

## Related

- `cmd/qclaw-launcher-tui/internal/ui/chat.go` — the implementation.
- `cmd/qclaw-launcher-tui/internal/ui/app.go` — `openChat()`, `isChatOpen`, `refreshMainMenu`.
- `pkg/agent/loop.go` — `ProcessDirectSingleTurnStream`, `ProcessAgenticWithProgressStream`.
- `pkg/providers/llamaserver/provider.go` — `ChatStream` (implements `providers.Streamable`).
- `pkg/providers/types.go` — `Streamable` interface definition.
- [`engines/yzma/lib/BUILD.md`](../../../engines/yzma/lib/BUILD.md) — `llama-server` HTTP API reference.
