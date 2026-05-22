// Package llamacli is a QClaw provider that drives the precompiled
// llama-cli binary shipped at engines/llamacli/mpu/llama-cli (the
// assix/Arduino-UnoQ-Optimized-Llama-CLI snapshot) as a subprocess per
// Chat() request.
//
// llama-cli is invoked with --json-schema so the model is constrained to
// emit either a text envelope ({"text":"..."}) or a tool-call envelope
// ({"tool_call":{"name":"...","arguments":{...}}}). The provider parses
// the envelope back into protocoltypes.LLMResponse.
//
// Note on cost: each Chat() spawns a fresh process that reloads the GGUF
// from disk (~5-15s for a 0.8B-Q4_0 model on the Uno Q). For multi-turn
// agent loops this is significant; a persistent-process variant is a
// follow-on (see pkg/providers/llamacli/README.md if present).
package llamacli

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/laurenvil/Uno-QClaw/pkg/providers/common"
	"github.com/laurenvil/Uno-QClaw/pkg/providers/protocoltypes"
)

type (
	Message        = protocoltypes.Message
	ToolDefinition = protocoltypes.ToolDefinition
	ToolCall       = protocoltypes.ToolCall
	FunctionCall   = protocoltypes.FunctionCall
	LLMResponse    = protocoltypes.LLMResponse
)

const defaultModelsDir = "~/models"

type Provider struct {
	binary       string
	modelsDir    string
	defaultModel string
	threads      int
	ctxSize      int
	timeout      time.Duration
}

type Option func(*Provider)

func WithTimeout(t time.Duration) Option {
	return func(p *Provider) {
		if t > 0 {
			p.timeout = t
		}
	}
}

func WithModelsDir(dir string) Option {
	return func(p *Provider) {
		if dir != "" {
			p.modelsDir = dir
		}
	}
}

func WithThreads(n int) Option {
	return func(p *Provider) {
		if n > 0 {
			p.threads = n
		}
	}
}

func WithContextSize(n int) Option {
	return func(p *Provider) {
		if n > 0 {
			p.ctxSize = n
		}
	}
}

func WithDefaultModel(name string) Option {
	return func(p *Provider) {
		if name != "" {
			p.defaultModel = name
		}
	}
}

func NewProvider(binary string, opts ...Option) *Provider {
	p := &Provider{
		binary:    binary,
		modelsDir: defaultModelsDir,
		threads:   4,
		ctxSize:   4096,
		timeout:   20 * time.Minute, // covers a cold model load on Uno Q
	}
	for _, opt := range opts {
		if opt != nil {
			opt(p)
		}
	}
	return p
}

func (p *Provider) Chat(
	ctx context.Context,
	messages []Message,
	tools []ToolDefinition,
	model string,
	options map[string]any,
) (*LLMResponse, error) {
	if p.binary == "" {
		return nil, errors.New("llama-cli binary path not configured")
	}
	modelPath, err := p.resolveModel(model)
	if err != nil {
		return nil, err
	}

	prompt := renderPrompt(messages)
	grammar := buildGrammar(tools)

	// Notes on this binary (assix-bundled llama-cli):
	//   - `-no-cnv` *enables* interactive mode in this fork (opposite of
	//     upstream). Use `-st` (--single-turn) with --prompt for one-shot
	//     non-interactive runs.
	//   - `--json-schema` / `--json-schema-file` are BROKEN here ("Failed
	//     to initialize samplers: std::exception"). `--grammar` works, so
	//     we hand-roll a GBNF grammar that matches our response envelopes.
	//   - `--reasoning off` disables the auto-`<think>` injection that
	//     Qwen 3.5 would otherwise add after the assistant turn; without
	//     it the model spends tokens thinking before reaching the
	//     constrained output region.
	args := []string{
		"-m", modelPath,
		"-st",
		"--reasoning", "off",
		"--grammar", grammar,
		"-c", fmt.Sprintf("%d", p.ctxSize),
		"-t", fmt.Sprintf("%d", p.threads),
		"-p", prompt,
	}
	if n, ok := common.AsInt(options["max_tokens"]); ok && n > 0 {
		args = append(args, "-n", fmt.Sprintf("%d", n))
	}
	if t, ok := common.AsFloat(options["temperature"]); ok {
		args = append(args, "--temp", fmt.Sprintf("%g", t))
	}

	cctx, cancel := context.WithTimeout(ctx, p.timeout)
	defer cancel()

	cmd := exec.CommandContext(cctx, p.binary, args...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("llama-cli exec failed: %w (stderr: %s)", err, truncate(stderr.String(), 1000))
	}

	payload, perr := extractJSON(stdout.String())
	if perr != nil {
		return nil, fmt.Errorf("parsing llama-cli output: %w (stdout: %s)", perr, truncate(stdout.String(), 500))
	}

	return parseEnvelope(payload)
}

func (p *Provider) resolveModel(model string) (string, error) {
	if model == "" {
		return "", errors.New("model name required")
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

// renderPrompt flattens messages into a ChatML-formatted prompt and opens
// the assistant turn so the model continues from there.
func renderPrompt(messages []Message) string {
	var b strings.Builder
	for _, m := range messages {
		role := m.Role
		switch role {
		case "system", "user", "assistant", "tool":
		default:
			role = "user"
		}
		b.WriteString("<|im_start|>")
		b.WriteString(role)
		b.WriteString("\n")
		b.WriteString(m.Content)
		b.WriteString("<|im_end|>\n")
	}
	b.WriteString("<|im_start|>assistant\n")
	return b.String()
}

// buildGrammar produces a GBNF grammar that accepts either a text envelope
// `{"text":"..."}` or, when tools are available, a tool envelope
// `{"tool_call":{"name":"<one-of>","arguments":<json>}}`.
//
// The arguments object is constrained only to be valid JSON (not to each
// tool's specific parameter schema) — full per-tool schema enforcement
// would require a JSON-schema-to-GBNF compiler, deferred until needed.
// In practice the model is reliable about producing the right shape when
// prompted with the tool definitions in the system message.
func buildGrammar(tools []ToolDefinition) string {
	var b strings.Builder

	if len(tools) == 0 {
		b.WriteString(`root ::= "{\"text\":" ws string ws "}"` + "\n")
	} else {
		var names []string
		for _, t := range tools {
			names = append(names, t.Function.Name)
		}
		b.WriteString(`root ::= text-env | tool-env` + "\n")
		b.WriteString(`text-env ::= "{\"text\":" ws string ws "}"` + "\n")
		b.WriteString(`tool-env ::= "{\"tool_call\":" ws "{\"name\":" ws tool-name ws ",\"arguments\":" ws json-value ws "}" ws "}"` + "\n")
		b.WriteString(`tool-name ::= ` + grammarQuotedLiteralAlternation(names) + "\n")
		b.WriteString(`json-value ::= object | array | string | number | "true" | "false" | "null"` + "\n")
		b.WriteString(`object ::= "{" ws (member ("," ws member)*)? ws "}"` + "\n")
		b.WriteString(`member ::= string ws ":" ws json-value` + "\n")
		b.WriteString(`array ::= "[" ws (json-value ("," ws json-value)*)? ws "]"` + "\n")
		b.WriteString(`number ::= "-"? ("0" | [1-9] [0-9]*) ("." [0-9]+)? ([eE] [+-]? [0-9]+)?` + "\n")
	}
	b.WriteString(`string ::= "\"" char* "\""` + "\n")
	b.WriteString(`char ::= [^"\\] | "\\" ["\\bfnrt/]` + "\n")
	b.WriteString(`ws ::= [ \t\n]*` + "\n")
	return b.String()
}

// grammarQuotedLiteralAlternation returns a GBNF alternation of the given
// names as JSON-quoted literals, e.g. ["a","b"] -> "\"a\"" | "\"b\"".
func grammarQuotedLiteralAlternation(names []string) string {
	parts := make([]string, 0, len(names))
	for _, n := range names {
		parts = append(parts, `"\"`+n+`\""`)
	}
	return strings.Join(parts, " | ")
}

// extractJSON returns the last top-level JSON object found in raw. llama-cli
// prints banners and timing info around the generated payload; the JSON we
// asked for is the final {...} block.
func extractJSON(raw string) (json.RawMessage, error) {
	closeIdx := strings.LastIndex(raw, "}")
	if closeIdx < 0 {
		return nil, errors.New("no '}' in output")
	}
	depth := 0
	openIdx := -1
	for i := closeIdx; i >= 0; i-- {
		switch raw[i] {
		case '}':
			depth++
		case '{':
			depth--
			if depth == 0 {
				openIdx = i
			}
		}
		if openIdx >= 0 {
			break
		}
	}
	if openIdx < 0 {
		return nil, errors.New("unmatched braces in output")
	}
	payload := strings.TrimSpace(raw[openIdx : closeIdx+1])
	var probe any
	if err := json.Unmarshal([]byte(payload), &probe); err != nil {
		return nil, fmt.Errorf("invalid JSON payload: %w", err)
	}
	return json.RawMessage(payload), nil
}

func parseEnvelope(payload json.RawMessage) (*LLMResponse, error) {
	var envelope struct {
		Text     string `json:"text,omitempty"`
		ToolCall *struct {
			Name      string         `json:"name"`
			Arguments map[string]any `json:"arguments"`
		} `json:"tool_call,omitempty"`
	}
	if err := json.Unmarshal(payload, &envelope); err != nil {
		return nil, err
	}
	if envelope.ToolCall != nil && envelope.ToolCall.Name != "" {
		argsBytes, err := json.Marshal(envelope.ToolCall.Arguments)
		if err != nil {
			return nil, fmt.Errorf("encoding tool args: %w", err)
		}
		return &LLMResponse{
			FinishReason: "tool_calls",
			ToolCalls: []ToolCall{{
				ID:   fmt.Sprintf("call_%d", time.Now().UnixNano()),
				Type: "function",
				Function: &FunctionCall{
					Name:      envelope.ToolCall.Name,
					Arguments: string(argsBytes),
				},
				Name:      envelope.ToolCall.Name,
				Arguments: envelope.ToolCall.Arguments,
			}},
		}, nil
	}
	return &LLMResponse{
		Content:      envelope.Text,
		FinishReason: "stop",
	}, nil
}

func (p *Provider) GetDefaultModel() string {
	return p.defaultModel
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
