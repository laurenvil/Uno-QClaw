package llamacli

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestRenderPrompt_ChatML(t *testing.T) {
	got := renderPrompt([]Message{
		{Role: "system", Content: "you are a duck"},
		{Role: "user", Content: "quack?"},
		{Role: "assistant", Content: "quack!"},
		{Role: "user", Content: "quack quack"},
	})
	for _, want := range []string{
		"<|im_start|>system\nyou are a duck<|im_end|>\n",
		"<|im_start|>user\nquack?<|im_end|>\n",
		"<|im_start|>assistant\nquack!<|im_end|>\n",
		"<|im_start|>user\nquack quack<|im_end|>\n",
	} {
		if !strings.Contains(got, want) {
			t.Errorf("renderPrompt missing block %q", want)
		}
	}
	if !strings.HasSuffix(got, "<|im_start|>assistant\n") {
		t.Errorf("renderPrompt should end with open assistant turn, got tail: %q", got[len(got)-50:])
	}
}

func TestBuildGrammar_TextOnly(t *testing.T) {
	g := buildGrammar(nil)
	if !strings.Contains(g, `root ::= "{\"text\":" ws string ws "}"`) {
		t.Errorf("text-only grammar missing root: %s", g)
	}
	if strings.Contains(g, "tool-env") {
		t.Errorf("text-only grammar should not include tool-env: %s", g)
	}
}

func TestBuildGrammar_WithTools_AlternatesEnvelopes(t *testing.T) {
	tools := []ToolDefinition{
		{Type: "function", Function: ToolFunctionDefinition{Name: "get_weather"}},
		{Type: "function", Function: ToolFunctionDefinition{Name: "send_email"}},
	}
	g := buildGrammar(tools)
	for _, want := range []string{
		"root ::= text-env | tool-env",
		`"\"get_weather\""`,
		`"\"send_email\""`,
		"json-value",
	} {
		if !strings.Contains(g, want) {
			t.Errorf("grammar missing %q in:\n%s", want, g)
		}
	}
}

// Import the typedef so tests can construct ToolFunctionDefinition without
// reaching into protocoltypes from this file.
type ToolFunctionDefinition = struct {
	Name        string         `json:"name"`
	Description string         `json:"description"`
	Parameters  map[string]any `json:"parameters"`
}

func TestExtractJSON_LastObject(t *testing.T) {
	raw := `Loading model...
build : b9099-5d5d2e15d
prompt eval time = ...
{"text":"hello there"}
llama_perf: total = ...`
	payload, err := extractJSON(raw)
	if err != nil {
		t.Fatalf("extractJSON err: %v", err)
	}
	if string(payload) != `{"text":"hello there"}` {
		t.Errorf("got %s", string(payload))
	}
}

func TestExtractJSON_NestedObject(t *testing.T) {
	raw := `banner
{"tool_call":{"name":"get_weather","arguments":{"location":"Boston"}}}
trailing`
	payload, err := extractJSON(raw)
	if err != nil {
		t.Fatalf("extractJSON err: %v", err)
	}
	var probe map[string]any
	if err := json.Unmarshal(payload, &probe); err != nil {
		t.Fatalf("not valid JSON: %v / %s", err, string(payload))
	}
	if _, ok := probe["tool_call"]; !ok {
		t.Errorf("missing tool_call key in %s", string(payload))
	}
}

func TestParseEnvelope_Text(t *testing.T) {
	resp, err := parseEnvelope(json.RawMessage(`{"text":"hi"}`))
	if err != nil {
		t.Fatal(err)
	}
	if resp.Content != "hi" || resp.FinishReason != "stop" {
		t.Errorf("got %+v", resp)
	}
	if len(resp.ToolCalls) != 0 {
		t.Errorf("expected no tool calls, got %d", len(resp.ToolCalls))
	}
}

func TestParseEnvelope_ToolCall(t *testing.T) {
	resp, err := parseEnvelope(json.RawMessage(
		`{"tool_call":{"name":"get_weather","arguments":{"location":"Boston","unit":"c"}}}`,
	))
	if err != nil {
		t.Fatal(err)
	}
	if resp.FinishReason != "tool_calls" {
		t.Errorf("finish_reason = %q, want tool_calls", resp.FinishReason)
	}
	if len(resp.ToolCalls) != 1 {
		t.Fatalf("expected 1 tool call, got %d", len(resp.ToolCalls))
	}
	tc := resp.ToolCalls[0]
	if tc.Function == nil || tc.Function.Name != "get_weather" {
		t.Errorf("tool name wrong: %+v", tc.Function)
	}
	var args map[string]any
	if err := json.Unmarshal([]byte(tc.Function.Arguments), &args); err != nil {
		t.Fatalf("args not JSON: %v", err)
	}
	if args["location"] != "Boston" {
		t.Errorf("args wrong: %+v", args)
	}
}

func TestResolveModel_AbsolutePathPassesThrough(t *testing.T) {
	p := NewProvider("/dev/null")
	got, err := p.resolveModel("/etc/hostname") // any existing file works
	if err != nil {
		t.Fatal(err)
	}
	if got != "/etc/hostname" {
		t.Errorf("got %s", got)
	}
}
