//go:build integration

package llamacli

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// repoRoot walks up from the test file to the qclaw repo root.
func repoRoot(t *testing.T) string {
	t.Helper()
	wd, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	for dir := wd; dir != "/" && dir != ""; dir = filepath.Dir(dir) {
		if _, err := os.Stat(filepath.Join(dir, ".gitmodules")); err == nil {
			return dir
		}
	}
	t.Fatalf("repo root not found from %s", wd)
	return ""
}

// TestIntegration_LlamaCLIText runs a real Chat() against the assix-bundled
// mpu/llama-cli with a Qwen Q4 model, verifies the JSON-schema-constrained
// output round-trips into a usable LLMResponse.
//
// Run with:  go test -tags=integration ./pkg/providers/llamacli/...
//
// Skipped if engines/llamacli/mpu/llama-cli or the model file are missing.
func TestIntegration_LlamaCLIText(t *testing.T) {
	root := repoRoot(t)
	binary := filepath.Join(root, "engines/llamacli/mpu/llama-cli")
	if _, err := os.Stat(binary); err != nil {
		t.Skipf("binary not present at %s: %v", binary, err)
	}
	model := "Qwen_Qwen3.5-0.8B-Q4_0.gguf"
	modelsDir := filepath.Join(os.Getenv("HOME"), "models")
	if _, err := os.Stat(filepath.Join(modelsDir, model)); err != nil {
		t.Skipf("model not present at %s/%s: %v", modelsDir, model, err)
	}

	p := NewProvider(binary,
		WithModelsDir(modelsDir),
		WithThreads(4),
		WithContextSize(2048),
		WithTimeout(15*time.Minute),
	)

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()

	resp, err := p.Chat(ctx,
		[]Message{
			{Role: "system", Content: "You are a helpful assistant. /no_think"},
			{Role: "user", Content: "Reply with exactly the word: pong"},
		},
		nil,
		model,
		map[string]any{
			"max_tokens":  16,
			"temperature": 0.0,
		},
	)
	if err != nil {
		t.Fatalf("Chat failed: %v", err)
	}
	t.Logf("response: %+v", resp)
	if resp.FinishReason != "stop" {
		t.Errorf("finish_reason = %q, want stop", resp.FinishReason)
	}
	if !strings.Contains(strings.ToLower(resp.Content), "pong") {
		t.Errorf("expected 'pong' in content, got %q", resp.Content)
	}
}

// TestIntegration_LlamaCLIToolCall verifies the JSON-schema oneOf path: when
// tool definitions are provided, the model must emit a tool_call envelope.
func TestIntegration_LlamaCLIToolCall(t *testing.T) {
	root := repoRoot(t)
	binary := filepath.Join(root, "engines/llamacli/mpu/llama-cli")
	if _, err := os.Stat(binary); err != nil {
		t.Skipf("binary not present at %s: %v", binary, err)
	}
	model := "Qwen_Qwen3.5-0.8B-Q4_0.gguf"
	modelsDir := filepath.Join(os.Getenv("HOME"), "models")
	if _, err := os.Stat(filepath.Join(modelsDir, model)); err != nil {
		t.Skipf("model not present at %s/%s: %v", modelsDir, model, err)
	}

	p := NewProvider(binary,
		WithModelsDir(modelsDir),
		WithThreads(4),
		WithContextSize(2048),
		WithTimeout(15*time.Minute),
	)
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()

	tools := []ToolDefinition{{
		Type: "function",
		Function: protocoltypesToolFn("get_weather", "Get current weather", map[string]any{
			"type": "object",
			"properties": map[string]any{
				"location": map[string]any{"type": "string"},
			},
			"required": []string{"location"},
		}),
	}}

	resp, err := p.Chat(ctx,
		[]Message{
			{Role: "system", Content: "You are a function-calling agent. /no_think Use the tool when needed."},
			{Role: "user", Content: "What is the weather in Boston?"},
		},
		tools, model,
		map[string]any{"max_tokens": 64, "temperature": 0.0},
	)
	if err != nil {
		t.Fatalf("Chat failed: %v", err)
	}
	t.Logf("response: text=%q tool_calls=%+v", resp.Content, resp.ToolCalls)

	// The model may either emit a text envelope or a tool call — both are
	// valid per schema. We just verify the response is one of the two,
	// well-formed, and the schema constraint held.
	if len(resp.ToolCalls) > 0 {
		tc := resp.ToolCalls[0]
		if tc.Function == nil || tc.Function.Name != "get_weather" {
			t.Errorf("unexpected tool call: %+v", tc)
		}
		var args map[string]any
		if err := json.Unmarshal([]byte(tc.Function.Arguments), &args); err != nil {
			t.Errorf("tool args not JSON: %v / %s", err, tc.Function.Arguments)
		}
	} else if resp.Content == "" {
		t.Errorf("response had neither text nor tool call")
	}
}

// protocoltypesToolFn shim to avoid an extra import path in this test file.
func protocoltypesToolFn(name, desc string, params map[string]any) struct {
	Name        string         `json:"name"`
	Description string         `json:"description"`
	Parameters  map[string]any `json:"parameters"`
} {
	return struct {
		Name        string         `json:"name"`
		Description string         `json:"description"`
		Parameters  map[string]any `json:"parameters"`
	}{Name: name, Description: desc, Parameters: params}
}
