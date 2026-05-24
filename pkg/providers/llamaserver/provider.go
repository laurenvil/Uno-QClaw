// Package llamaserver is a QClaw provider that manages a persistent
// llama-server process (from the assix/llama.cpp fork) and communicates
// with it via its OpenAI-compatible HTTP API.
//
// This architecture fixes the "no '}' in output" error common in the
// one-shot llama-cli provider by using a structured JSON API instead
// of scraping stdout. It also eliminates the ~15s cold-start cost per message.
package llamaserver

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/laurenvil/Uno-QClaw/pkg/logger"
	"github.com/laurenvil/Uno-QClaw/pkg/providers/common"
	"github.com/laurenvil/Uno-QClaw/pkg/providers/openai_compat"
	"github.com/laurenvil/Uno-QClaw/pkg/providers/protocoltypes"
)

type (
	Message        = protocoltypes.Message
	ToolDefinition = protocoltypes.ToolDefinition
	LLMResponse    = protocoltypes.LLMResponse
)

const (
	defaultPort      = 8080
	defaultHost      = "127.0.0.1"
	healthCheckLimit = 30
)

type Provider struct {
	binary      string
	modelPath   string
	modelsDir   string
	threads     int
	ctxSize     int
	port        int
	host        string
	timeout     time.Duration
	extraArgs   []string
	libraryPath string

	// Internal state
	cmd         *exec.Cmd
	inner       *openai_compat.Provider
	mu          sync.Mutex
	initialized bool
}

type Option func(*Provider)

func WithTimeout(t time.Duration) Option {
	return func(p *Provider) { p.timeout = t }
}

func WithModelsDir(dir string) Option {
	return func(p *Provider) { p.modelsDir = dir }
}

func WithThreads(n int) Option {
	return func(p *Provider) { p.threads = n }
}

func WithContextSize(n int) Option {
	return func(p *Provider) { p.ctxSize = n }
}

func WithPort(port int) Option {
	return func(p *Provider) { p.port = port }
}

func WithExtraArgs(args []string) Option {
	return func(p *Provider) { p.extraArgs = args }
}

// WithLibraryPath prepends a directory to LD_LIBRARY_PATH when spawning the
// llama-server subprocess. Required for dynamically-linked builds whose
// ggml/llama .so files live next to the binary instead of a system path.
func WithLibraryPath(path string) Option {
	return func(p *Provider) { p.libraryPath = path }
}

func NewProvider(binary string, opts ...Option) *Provider {
	p := &Provider{
		binary:    binary,
		modelsDir: "~/models",
		threads:   4,
		ctxSize:   4096,
		port:      defaultPort,
		host:      defaultHost,
		timeout:   20 * time.Minute, // match llamacli default for cold prefill
	}
	for _, opt := range opts {
		if opt != nil {
			opt(p)
		}
	}
	
	apiBase := fmt.Sprintf("http://%s:%d/v1", p.host, p.port)
	p.inner = openai_compat.NewProvider("", apiBase, "",
		openai_compat.WithRequestTimeout(p.timeout))
	
	return p
}

func (p *Provider) Chat(
	ctx context.Context,
	messages []Message,
	tools []ToolDefinition,
	model string,
	options map[string]any,
) (*LLMResponse, error) {
	if err := p.ensureServer(ctx, model); err != nil {
		return nil, fmt.Errorf("llama-server initialization failed: %w", err)
	}
	
	return p.inner.Chat(ctx, messages, tools, model, options)
}

func (p *Provider) GetDefaultModel() string {
	return ""
}

// ChatStream implements providers.Streamable for the persistent llama-server.
// It POSTs a streaming /v1/chat/completions request and reads the
// OpenAI-style SSE response, dispatching content deltas live to onToken and
// accumulating tool_calls deltas indexed by their slot. The assembled
// LLMResponse — content + tool_calls — is returned when [DONE] arrives.
//
// Tool-aware: when tools are passed, llama-server is asked to choose among
// them (tool_choice: auto). The model may emit text, tool_calls, or both
// in one response — content streams to the user immediately; tool_calls
// stay buffered until the stream completes so the agent loop can dispatch
// them as a unit.
func (p *Provider) ChatStream(
	ctx context.Context,
	messages []Message,
	tools []ToolDefinition,
	model string,
	options map[string]any,
	onToken func(string),
) (*LLMResponse, error) {
	if err := p.ensureServer(ctx, model); err != nil {
		return nil, fmt.Errorf("llama-server initialization failed: %w", err)
	}

	// Strip protocol prefix ("llama-server/modelname" → "modelname").
	if _, after, ok := strings.Cut(model, "/"); ok {
		model = after
	}

	body := map[string]any{
		"model":    model,
		"messages": common.SerializeMessages(messages),
		"stream":   true,
	}
	if len(tools) > 0 {
		body["tools"] = tools
		body["tool_choice"] = "auto"
	}
	if n, ok := common.AsInt(options["max_tokens"]); ok && n > 0 {
		body["max_tokens"] = n
	}
	if t, ok := common.AsFloat(options["temperature"]); ok {
		body["temperature"] = t
	}

	jsonData, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal stream request: %w", err)
	}

	url := fmt.Sprintf("http://%s:%d/v1/chat/completions", p.host, p.port)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create stream request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")

	// No client timeout — context cancellation handles it.
	resp, err := (&http.Client{}).Do(req)
	if err != nil {
		return nil, fmt.Errorf("stream request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		errBody, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("llama-server returned %d: %s", resp.StatusCode, errBody)
	}

	type tcAccum struct {
		id        string
		typ       string
		name      string
		arguments strings.Builder
	}

	var (
		contentSB    strings.Builder
		finishReason string
		toolAccs     = map[int]*tcAccum{}
	)

	scanner := bufio.NewScanner(resp.Body)
	// Generous buffer — individual SSE lines stay small but tool_calls deltas
	// with long argument payloads occasionally push past the default 64 KiB.
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)

	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "data: ") {
			continue
		}
		payload := line[6:]
		if payload == "[DONE]" {
			break
		}
		var chunk struct {
			Choices []struct {
				Delta struct {
					Content   string `json:"content"`
					ToolCalls []struct {
						Index    int    `json:"index"`
						ID       string `json:"id,omitempty"`
						Type     string `json:"type,omitempty"`
						Function struct {
							Name      string `json:"name,omitempty"`
							Arguments string `json:"arguments,omitempty"`
						} `json:"function"`
					} `json:"tool_calls"`
				} `json:"delta"`
				FinishReason string `json:"finish_reason"`
			} `json:"choices"`
		}
		if err := json.Unmarshal([]byte(payload), &chunk); err != nil {
			continue
		}
		if len(chunk.Choices) == 0 {
			continue
		}
		choice := chunk.Choices[0]

		if tok := choice.Delta.Content; tok != "" {
			contentSB.WriteString(tok)
			if onToken != nil {
				onToken(tok)
			}
		}

		for _, dtc := range choice.Delta.ToolCalls {
			acc, ok := toolAccs[dtc.Index]
			if !ok {
				acc = &tcAccum{}
				toolAccs[dtc.Index] = acc
			}
			if dtc.ID != "" {
				acc.id = dtc.ID
			}
			if dtc.Type != "" {
				acc.typ = dtc.Type
			}
			if dtc.Function.Name != "" {
				acc.name = dtc.Function.Name
			}
			if dtc.Function.Arguments != "" {
				acc.arguments.WriteString(dtc.Function.Arguments)
			}
		}

		if choice.FinishReason != "" {
			finishReason = choice.FinishReason
		}
	}
	if err := scanner.Err(); err != nil && err != io.EOF {
		return nil, fmt.Errorf("stream read error: %w", err)
	}

	resp_ := &LLMResponse{
		Content:      contentSB.String(),
		FinishReason: finishReason,
	}
	if len(toolAccs) > 0 {
		// Emit in index order so tool dispatch is deterministic.
		indices := make([]int, 0, len(toolAccs))
		for i := range toolAccs {
			indices = append(indices, i)
		}
		sort.Ints(indices)
		for _, i := range indices {
			acc := toolAccs[i]
			resp_.ToolCalls = append(resp_.ToolCalls, protocoltypes.ToolCall{
				ID:   acc.id,
				Type: acc.typ,
				Function: &protocoltypes.FunctionCall{
					Name:      acc.name,
					Arguments: acc.arguments.String(),
				},
			})
		}
	}
	return resp_, nil
}

func (p *Provider) Close() {
	p.mu.Lock()
	defer p.mu.Unlock()
	
	if p.cmd != nil && p.cmd.Process != nil {
		logger.InfoCF("llamaserver", "Stopping persistent llama-server", nil)
		p.cmd.Process.Kill()
		p.cmd.Wait()
		p.cmd = nil
	}
	p.initialized = false
}

func (p *Provider) ensureServer(ctx context.Context, model string) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	
	if p.initialized {
		// Check if process is still alive
		if p.cmd != nil && p.cmd.ProcessState != nil && p.cmd.ProcessState.Exited() {
			logger.WarnCF("llamaserver", "llama-server process exited, restarting", nil)
			p.initialized = false
		} else {
			return nil
		}
	}

	modelPath, err := p.resolveModel(model)
	if err != nil {
		return err
	}
	
	args := []string{
		"-m", modelPath,
		"--host", p.host,
		"--port", fmt.Sprintf("%d", p.port),
		"-t", fmt.Sprintf("%d", p.threads),
		"-c", fmt.Sprintf("%d", p.ctxSize),
		"--reasoning", "off", // Disable Qwen 3.5 auto-<think> injection
		"--jinja",           // Enable template-based tool calling
		"--log-disable",     // Keep stdout clean
	}
	args = append(args, p.extraArgs...)
	
	logger.InfoCF("llamaserver", "Starting persistent llama-server", map[string]any{
		"binary": p.binary,
		"model":  filepath.Base(modelPath),
		"port":   p.port,
	})
	
	cmd := exec.Command(p.binary, args...)
	if p.libraryPath != "" {
		existing := os.Getenv("LD_LIBRARY_PATH")
		ldPath := p.libraryPath
		if existing != "" {
			ldPath = p.libraryPath + ":" + existing
		}
		cmd.Env = append(os.Environ(), "LD_LIBRARY_PATH="+ldPath)
	}
	// Redirect logs to nowhere or a file if we wanted
	cmd.Stderr = os.Stderr

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("failed to start llama-server: %w", err)
	}
	
	p.cmd = cmd
	
	// Wait for health check
	healthURL := fmt.Sprintf("http://%s:%d/health", p.host, p.port)
	ready := false
	for i := 0; i < healthCheckLimit; i++ {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
			resp, err := http.Get(healthURL)
			if err == nil && resp.StatusCode == http.StatusOK {
				ready = true
				break
			}
			if resp != nil {
				resp.Body.Close()
			}
			time.Sleep(1 * time.Second)
		}
		if ready {
			break
		}
	}
	
	if !ready {
		p.Close()
		return fmt.Errorf("llama-server failed to become healthy within %d seconds", healthCheckLimit)
	}
	
	p.initialized = true
	return nil
}

func (p *Provider) resolveModel(model string) (string, error) {
	if model == "" {
		return "", fmt.Errorf("model name required")
	}
	if filepath.IsAbs(model) || strings.HasPrefix(model, "./") || strings.HasPrefix(model, "../") {
		return model, nil
	}
	dir := expandHome(p.modelsDir)
	candidate := filepath.Join(dir, model)
	if _, err := os.Stat(candidate); err == nil {
		return candidate, nil
	}
	if !strings.HasSuffix(model, ".gguf") {
		candidate = filepath.Join(dir, model+".gguf")
		if _, err := os.Stat(candidate); err == nil {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("model %q not found under %s", model, dir)
}

func expandHome(p string) string {
	if !strings.HasPrefix(p, "~/") {
		return p
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return p
	}
	return filepath.Join(home, p[2:])
}
