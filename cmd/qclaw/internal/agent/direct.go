package agent

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"

	"github.com/ergochat/readline"
	"github.com/spf13/cobra"

	"github.com/laurenvil/Uno-QClaw/cmd/qclaw/internal"
	"github.com/laurenvil/Uno-QClaw/pkg/agent"
	"github.com/laurenvil/Uno-QClaw/pkg/bus"
	"github.com/laurenvil/Uno-QClaw/pkg/logger"
	"github.com/laurenvil/Uno-QClaw/pkg/providers"
)

// runDirectTurn runs a single direct turn with a thinking spinner that
// clears on the first streamed token, followed by live token output and a
// trailing elapsed-time summary. Returns the assembled response.
func runDirectTurn(ctx context.Context, agentLoop *agent.AgentLoop, input, sessionKey string) (string, error) {
	spin := startSpinner("QClaw is thinking…")
	var firstToken atomic.Bool

	fmt.Print("\nQClaw (direct): ")
	onToken := func(tok string) {
		if firstToken.CompareAndSwap(false, true) {
			spin.Stop()
			// re-print the label since the spinner cleared the line on stop
			fmt.Print("\nQClaw (direct): ")
		}
		fmt.Print(tok)
	}

	response, err := agentLoop.ProcessDirectSingleTurnStream(ctx, input, sessionKey, onToken)
	elapsed := spin.Elapsed()
	spin.Stop()

	if err != nil {
		return "", err
	}

	// If streaming never engaged (e.g. provider didn't implement Streamable),
	// emit the full response now so the user sees something.
	if !firstToken.Load() {
		fmt.Print(response)
	}
	fmt.Printf("\n  ⏱  %s\n\n", elapsed.Round(100*1000*1000)) // .1s precision
	return response, nil
}

func NewDirectCommand() *cobra.Command {
	var (
		message    string
		sessionKey string
		model      string
		debug      bool
	)

	cmd := &cobra.Command{
		Use:   "direct",
		Short: "Interact with the agent in direct mode (single-turn, no tools)",
		Long:  "Direct mode uses the same pre-router and skills as agentic mode, but skips the tool loop for faster Q&A.",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			return directCmd(message, sessionKey, model, debug)
		},
	}

	cmd.Flags().BoolVarP(&debug, "debug", "d", false, "Enable debug logging")
	cmd.Flags().StringVarP(&message, "message", "m", "", "Send a single message")
	cmd.Flags().StringVarP(&sessionKey, "session", "s", "cli:direct", "Session key")
	cmd.Flags().StringVarP(&model, "model", "", "", "Model to use")

	return cmd
}

func directCmd(message, sessionKey, model string, debug bool) error {
	if sessionKey == "" {
		sessionKey = "cli:direct"
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

	if modelID != "" {
		cfg.Agents.Defaults.ModelName = modelID
	}

	msgBus := bus.NewMessageBus()
	defer msgBus.Close()
	agentLoop := agent.NewAgentLoop(cfg, msgBus, provider)
	defer agentLoop.Close()

	if message != "" {
		ctx := context.Background()
		if _, err := runDirectTurn(ctx, agentLoop, message, sessionKey); err != nil {
			return fmt.Errorf("error processing message: %w", err)
		}
		return nil
	}

	fmt.Printf("QClaw (direct) is ready — type your question below (type 'exit' to quit)\n\n")
	directInteractiveMode(agentLoop, sessionKey)

	return nil
}

func directInteractiveMode(agentLoop *agent.AgentLoop, sessionKey string) {
	prompt := "Direct You: "

	rl, err := readline.NewEx(&readline.Config{
		Prompt:          prompt,
		HistoryFile:     filepath.Join(os.TempDir(), ".qclaw_direct_history"),
		HistoryLimit:    100,
		InterruptPrompt: "^C",
		EOFPrompt:       "exit",
	})
	if err != nil {
		fmt.Printf("Error initializing readline: %v\n", err)
		simpleDirectInteractiveMode(agentLoop, sessionKey)
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
			continue
		}

		input := strings.TrimSpace(line)
		if input == "" {
			continue
		}

		if input == "exit" || input == "quit" {
			return
		}

		ctx := context.Background()
		if _, err := runDirectTurn(ctx, agentLoop, input, sessionKey); err != nil {
			fmt.Printf("Error: %v\n", err)
			continue
		}
	}
}

func simpleDirectInteractiveMode(agentLoop *agent.AgentLoop, sessionKey string) {
	reader := bufio.NewReader(os.Stdin)
	for {
		fmt.Print("Direct You: ")
		line, err := reader.ReadString('\n')
		if err != nil {
			return
		}

		input := strings.TrimSpace(line)
		if input == "" {
			continue
		}

		if input == "exit" || input == "quit" {
			return
		}

		ctx := context.Background()
		if _, err := runDirectTurn(ctx, agentLoop, input, sessionKey); err != nil {
			fmt.Printf("Error: %v\n", err)
			continue
		}
	}
}
