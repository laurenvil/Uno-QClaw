// Package llamaserver is a QClaw provider that manages a persistent
// llama-server process (from the assix/llama.cpp fork) and communicates
// with it via its OpenAI-compatible HTTP API.
//
// This architecture fixes the "no '}' in output" error common in the
// one-shot llama-cli provider by using a structured JSON API instead
// of scraping stdout. It also eliminates the ~15s cold-start cost per message.
package llamaserver

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/laurenvil/Uno-QClaw/pkg/logger"
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
