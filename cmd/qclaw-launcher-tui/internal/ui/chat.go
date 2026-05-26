package ui

import (
	"context"
	"fmt"
	"strings"
	"sync/atomic"

	"github.com/gdamore/tcell/v2"
	"github.com/rivo/tview"

	configstore "github.com/laurenvil/Uno-QClaw/cmd/qclaw-launcher-tui/internal/config"
	"github.com/laurenvil/Uno-QClaw/pkg/agent"
	"github.com/laurenvil/Uno-QClaw/pkg/bus"
	"github.com/laurenvil/Uno-QClaw/pkg/providers"
)

type chatMode int

const (
	chatModeDirect  chatMode = iota
	chatModeAgentic chatMode = iota
)

// chatPage holds the TUI state for the in-app chat surface.
// It supports two modes:
//   - Direct:  pre-router + single LLM call, token streaming via ProcessDirectSingleTurnStream
//   - Agentic: full tool loop + streaming via ProcessAgenticWithProgressStream
//
// F2 toggles mode; each toggle clears output and starts a fresh session.
// ESC cancels any in-flight request and returns to the main menu.
type chatPage struct {
	s       *appState
	flex    *tview.Flex
	modeBar *tview.TextView
	output  *tview.TextView
	input   *tview.InputField

	loop   *agent.AgentLoop
	msgBus *bus.MessageBus
	ctx    context.Context
	cancel context.CancelFunc

	prov      providers.LLMProvider // raw provider, used for WarmUp type assertion
	modelName string                // model file name passed to provider (e.g. "Qwen3.5-0.8B-Q6_K")
	engineKey string                // engine display key (e.g. "yzma"), shown in mode bar

	mode      chatMode
	toggleCtr int // bumped on each mode toggle to create a fresh session key
	busy      atomic.Bool
}

func (s *appState) newChatPage() (*chatPage, error) {
	// Load a fresh config to avoid mutating the TUI's shared s.config
	// (providers.CreateProvider may set ModelName on the config it receives).
	cfg, err := configstore.Load()
	if err != nil {
		return nil, fmt.Errorf("loading config: %w", err)
	}

	prov, modelID, err := providers.CreateProvider(cfg)
	if err != nil {
		return nil, fmt.Errorf("creating provider: %w", err)
	}
	if modelID != "" {
		cfg.Agents.Defaults.ModelName = modelID
	}

	msgBus := bus.NewMessageBus()
	loop := agent.NewAgentLoop(cfg, msgBus, prov)
	ctx, cancel := context.WithCancel(context.Background())

	engineKey := strings.TrimSpace(cfg.Agents.Defaults.Model)
	if engineKey == "" {
		engineKey = "?"
	}

	cp := &chatPage{
		s:         s,
		loop:      loop,
		msgBus:    msgBus,
		ctx:       ctx,
		cancel:    cancel,
		prov:      prov,
		modelName: cfg.Agents.Defaults.ModelName,
		engineKey: engineKey,
	}
	cp.build()
	return cp, nil
}

func (cp *chatPage) build() {
	s := cp.s

	// ── Mode bar ──────────────────────────────────────────────────────────────
	cp.modeBar = tview.NewTextView().SetDynamicColors(true)
	cp.modeBar.SetBackgroundColor(tview.Styles.MoreContrastBackgroundColor)

	// ── Output pane ───────────────────────────────────────────────────────────
	cp.output = tview.NewTextView().
		SetDynamicColors(true).
		SetWordWrap(true).
		SetScrollable(true)
	cp.output.SetBorder(true)

	// ── Input field ───────────────────────────────────────────────────────────
	cp.input = tview.NewInputField().
		SetLabel("You: ").
		SetLabelColor(tcell.NewRGBColor(139, 233, 253)).
		SetFieldBackgroundColor(tview.Styles.PrimitiveBackgroundColor).
		SetFieldTextColor(tview.Styles.PrimaryTextColor)
	cp.input.SetBorder(true).SetTitle(" Message ")

	cp.input.SetInputCapture(func(event *tcell.EventKey) *tcell.EventKey {
		if event.Key() == tcell.KeyEsc {
			cp.close()
			return nil
		}
		return event
	})

	cp.input.SetDoneFunc(func(key tcell.Key) {
		if key != tcell.KeyEnter {
			return
		}
		text := strings.TrimSpace(cp.input.GetText())
		if text == "" || cp.busy.Load() {
			return
		}
		cp.input.SetText("")
		cp.dispatch(text)
	})

	// ── Outer flex ────────────────────────────────────────────────────────────
	cp.flex = tview.NewFlex().SetDirection(tview.FlexRow)
	cp.flex.SetBorder(true).SetTitle(" Chat ")
	cp.flex.SetInputCapture(func(event *tcell.EventKey) *tcell.EventKey {
		switch event.Key() {
		case tcell.KeyF2:
			if !cp.busy.Load() {
				cp.toggleMode()
			}
			return nil
		case tcell.KeyCtrlL:
			s.app.QueueUpdateDraw(func() { cp.output.Clear() })
			return nil
		}
		return event
	})

	cp.flex.AddItem(cp.modeBar, 1, 0, false)
	cp.flex.AddItem(cp.output, 0, 1, false)
	cp.flex.AddItem(cp.input, 3, 0, true)

	cp.updateModeBar()
}

// updateModeBar rewrites the mode bar text. Must be called from the main goroutine.
func (cp *chatPage) updateModeBar() {
	var sb strings.Builder
	if cp.mode == chatModeDirect {
		sb.WriteString(" [#50fa7b]● Direct[-]  [gray]○ Agentic[-]")
	} else {
		sb.WriteString(" [gray]○ Direct[-]  [#50fa7b]● Agentic[-]")
	}
	fmt.Fprintf(&sb, "  │  [#bd93f9]%s[-]  │  F2:mode  Ctrl+L:clear  Esc:back", cp.engineKey)
	cp.modeBar.SetText(sb.String())
}

// toggleMode switches between Direct and Agentic, clears the output, and starts a fresh session.
func (cp *chatPage) toggleMode() {
	cp.toggleCtr++
	if cp.mode == chatModeDirect {
		cp.mode = chatModeAgentic
	} else {
		cp.mode = chatModeDirect
	}
	cp.output.Clear()
	cp.updateModeBar()
}

// sessionKey returns a unique key for the current mode+toggle generation.
func (cp *chatPage) sessionKey() string {
	if cp.mode == chatModeDirect {
		return fmt.Sprintf("tui:direct:%d", cp.toggleCtr)
	}
	return fmt.Sprintf("tui:agentic:%d", cp.toggleCtr)
}

// dispatch is the entry point for a new user message. Always called from the main goroutine.
func (cp *chatPage) dispatch(text string) {
	if !cp.busy.CompareAndSwap(false, true) {
		return
	}

	// Write user turn + QClaw response prefix (safe: we are on the main goroutine).
	fmt.Fprintf(cp.output, "[#8be9fd]You:[-] %s\n[#f1faff]QClaw:[-] ", tview.Escape(text))
	cp.output.ScrollToEnd()
	cp.input.SetPlaceholder("⊙ thinking…")

	mode := cp.mode
	skey := cp.sessionKey()

	go func() {
		defer func() {
			if cp.ctx.Err() != nil {
				return // page is closing — do not touch UI primitives
			}
			cp.busy.Store(false)
			cp.s.app.QueueUpdateDraw(func() {
				cp.input.SetPlaceholder("")
				cp.s.app.SetFocus(cp.input)
			})
		}()

		var callErr error
		if mode == chatModeDirect {
			callErr = cp.runDirect(text, skey)
		} else {
			callErr = cp.runAgentic(text, skey)
		}

		if cp.ctx.Err() != nil {
			return
		}

		cp.s.app.QueueUpdateDraw(func() {
			if callErr != nil {
				fmt.Fprintf(cp.output, "\n[#ff5555]Error: %s[-]", tview.Escape(callErr.Error()))
			}
			fmt.Fprint(cp.output, "\n\n")
			cp.output.ScrollToEnd()
		})
	}()
}

// runDirect calls ProcessDirectSingleTurnStream and streams tokens into the output pane.
func (cp *chatPage) runDirect(text, sessionKey string) error {
	var firstToken atomic.Bool

	onToken := func(tok string) {
		if cp.ctx.Err() != nil {
			return
		}
		isFirst := firstToken.CompareAndSwap(false, true)
		cp.s.app.QueueUpdateDraw(func() {
			if isFirst {
				cp.input.SetPlaceholder("")
			}
			fmt.Fprint(cp.output, tview.Escape(tok))
			cp.output.ScrollToEnd()
		})
	}

	resp, err := cp.loop.ProcessDirectSingleTurnStream(cp.ctx, text, sessionKey, onToken)
	if err != nil {
		return err
	}

	// If the provider didn't stream (no Streamable implementation), print the full response.
	if !firstToken.Load() {
		cp.s.app.QueueUpdateDraw(func() {
			fmt.Fprint(cp.output, tview.Escape(resp))
			cp.output.ScrollToEnd()
		})
	}

	return nil
}

// runAgentic calls ProcessAgenticWithProgressStream, renders tool progress inline,
// and streams content tokens into the output pane.
func (cp *chatPage) runAgentic(text, sessionKey string) error {
	var firstToken atomic.Bool
	var placeholderCleared atomic.Bool

	clearPlaceholder := func() {
		if placeholderCleared.CompareAndSwap(false, true) {
			cp.s.app.QueueUpdateDraw(func() {
				cp.input.SetPlaceholder("")
			})
		}
	}

	onProgress := func(ev agent.ProgressEvent) {
		if cp.ctx.Err() != nil {
			return
		}
		var line string
		switch ev.Kind {
		case "tool_start":
			args := ev.Arguments
			if len(args) > 100 {
				args = args[:100] + "…"
			}
			line = fmt.Sprintf("[#bd93f9]⚙ %s(%s)[-]\n", tview.Escape(ev.Tool), tview.Escape(args))
		case "tool_done":
			line = fmt.Sprintf("[#50fa7b]✓ %s[-]\n", tview.Escape(ev.Message))
		case "tool_error":
			line = fmt.Sprintf("[#ff5555]✗ %s[-]\n", tview.Escape(ev.Message))
		}
		if line != "" {
			clearPlaceholder()
			cp.s.app.QueueUpdateDraw(func() {
				fmt.Fprint(cp.output, line)
				cp.output.ScrollToEnd()
			})
		}
	}

	onToken := func(tok string) {
		if cp.ctx.Err() != nil {
			return
		}
		isFirst := firstToken.CompareAndSwap(false, true)
		cp.s.app.QueueUpdateDraw(func() {
			// Inline the placeholder clear — must not call QueueUpdateDraw again from here.
			if isFirst && placeholderCleared.CompareAndSwap(false, true) {
				cp.input.SetPlaceholder("")
			}
			fmt.Fprint(cp.output, tview.Escape(tok))
			cp.output.ScrollToEnd()
		})
	}

	resp, err := cp.loop.ProcessAgenticWithProgressStream(cp.ctx, text, sessionKey, onProgress, onToken)
	if err != nil {
		return err
	}

	if !firstToken.Load() {
		cp.s.app.QueueUpdateDraw(func() {
			fmt.Fprint(cp.output, tview.Escape(resp))
			cp.output.ScrollToEnd()
		})
	}

	return nil
}

// preWarm triggers llama-server start without an LLM call if the provider supports it.
// Blocks until the server is ready (or fails). Safe to call from any goroutine.
func (cp *chatPage) preWarm(ctx context.Context) {
	type warmUpper interface {
		WarmUp(ctx context.Context, model string) error
	}
	wu, ok := cp.prov.(warmUpper)
	if !ok {
		return
	}
	_ = wu.WarmUp(ctx, cp.modelName)
}

// close cancels any in-flight request, shuts down the agent loop, and returns to the main menu.
// Must be called from the main goroutine.
func (cp *chatPage) close() {
	cp.cancel()
	s := cp.s
	go func() {
		cp.loop.Close()
		cp.msgBus.Close()
		// Re-warm a fresh page after the old server has fully stopped.
		go s.triggerPrewarm()
	}()
	s.isChatOpen = false
	s.pop()
}
