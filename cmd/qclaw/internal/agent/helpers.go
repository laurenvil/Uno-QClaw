package agent

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/ergochat/readline"

	"github.com/laurenvil/Uno-QClaw/cmd/qclaw/internal"
	"github.com/laurenvil/Uno-QClaw/pkg/agent"
	"github.com/laurenvil/Uno-QClaw/pkg/bus"
	"github.com/laurenvil/Uno-QClaw/pkg/logger"
	"github.com/laurenvil/Uno-QClaw/pkg/providers"
)

// runAgenticTurn runs one turn of the agentic CLI with a thinking spinner
// that shows live tool-call progress and elapsed time.
func runAgenticTurn(ctx context.Context, agentLoop *agent.AgentLoop, input, sessionKey string) (string, error) {
	spin := startSpinner("QClaw is thinking…")

	progress := func(ev agent.ProgressEvent) {
		spin.Clear()
		switch ev.Kind {
		case "tool_start":
			fmt.Fprintf(os.Stderr, "  🔧 %s\n", ev.Message)
			spin.SetLabel(fmt.Sprintf("Running %s…", ev.Tool))
		case "tool_done":
			fmt.Fprintf(os.Stderr, "  ✓  %s (%s)\n", ev.Message, ev.Elapsed.Round(100*1000*1000))
			spin.SetLabel("QClaw is thinking…")
		case "tool_error":
			fmt.Fprintf(os.Stderr, "  ✗  %s (%s)\n", ev.Message, ev.Elapsed.Round(100*1000*1000))
			spin.SetLabel("QClaw is thinking…")
		}
	}

	response, err := agentLoop.ProcessDirectWithProgress(ctx, input, sessionKey, progress)
	elapsed := spin.Elapsed()
	spin.Stop()
	if err != nil {
		return "", err
	}
	fmt.Printf("\nQClaw: %s\n  ⏱  %s\n\n", response, elapsed.Round(100*1000*1000))
	return response, nil
}

func agentCmd(message, sessionKey, model string, debug bool) error {
	if sessionKey == "" {
		sessionKey = "cli:default"
	}

	if debug {
		logger.SetLevel(logger.DEBUG)
		fmt.Println("🔍 Debug mode enabled")
	}

	cfg, err := internal.LoadConfig()
	if err != nil {
		return fmt.Errorf("error loading config: %w", err)
	}

	if model != "" {
		cfg.Agents.Defaults.ModelName = model
	}

	provider, modelID, err := providers.CreateProvider(cfg)
	if err != nil {
		return fmt.Errorf("error creating provider: %w", err)
	}

	// Use the resolved model ID from provider creation
	if modelID != "" {
		cfg.Agents.Defaults.ModelName = modelID
	}

	msgBus := bus.NewMessageBus()
	defer msgBus.Close()
	agentLoop := agent.NewAgentLoop(cfg, msgBus, provider)
	defer agentLoop.Close()

	// Print agent startup info (only for interactive mode)
	startupInfo := agentLoop.GetStartupInfo()
	logger.InfoCF("agent", "Agent initialized",
		map[string]any{
			"tools_count":      startupInfo["tools"].(map[string]any)["count"],
			"skills_total":     startupInfo["skills"].(map[string]any)["total"],
			"skills_available": startupInfo["skills"].(map[string]any)["available"],
		})

	if message != "" {
		ctx := context.Background()
		if _, err := runAgenticTurn(ctx, agentLoop, message, sessionKey); err != nil {
			return fmt.Errorf("error processing message: %w", err)
		}
		return nil
	}

	fmt.Printf("QClaw is ready — type your question below (type 'exit' to quit)\n\n")
	interactiveMode(agentLoop, sessionKey)

	return nil
}

func interactiveMode(agentLoop *agent.AgentLoop, sessionKey string) {
	prompt := "You: "

	rl, err := readline.NewEx(&readline.Config{
		Prompt:          prompt,
		HistoryFile:     filepath.Join(os.TempDir(), ".qclaw_history"),
		HistoryLimit:    100,
		InterruptPrompt: "^C",
		EOFPrompt:       "exit",
	})
	if err != nil {
		fmt.Printf("Error initializing readline: %v\n", err)
		fmt.Println("Falling back to simple input mode...")
		simpleInteractiveMode(agentLoop, sessionKey)
		return
	}
	defer rl.Close()

	for {
		line, err := rl.Readline()
		if err != nil {
			if err == readline.ErrInterrupt || err == io.EOF {
				fmt.Println("\nGoodbye!")
				return
			}
			fmt.Printf("Error reading input: %v\n", err)
			continue
		}

		input := strings.TrimSpace(line)
		if input == "" {
			continue
		}

		if input == "exit" || input == "quit" {
			fmt.Println("Goodbye!")
			return
		}

		ctx := context.Background()
		if _, err := runAgenticTurn(ctx, agentLoop, input, sessionKey); err != nil {
			fmt.Printf("Error: %v\n", err)
			continue
		}
	}
}

func simpleInteractiveMode(agentLoop *agent.AgentLoop, sessionKey string) {
	reader := bufio.NewReader(os.Stdin)
	for {
		fmt.Print("You: ")
		line, err := reader.ReadString('\n')
		if err != nil {
			if err == io.EOF {
				fmt.Println("\nGoodbye!")
				return
			}
			fmt.Printf("Error reading input: %v\n", err)
			continue
		}

		input := strings.TrimSpace(line)
		if input == "" {
			continue
		}

		if input == "exit" || input == "quit" {
			fmt.Println("Goodbye!")
			return
		}

		ctx := context.Background()
		if _, err := runAgenticTurn(ctx, agentLoop, input, sessionKey); err != nil {
			fmt.Printf("Error: %v\n", err)
			continue
		}
	}
}
