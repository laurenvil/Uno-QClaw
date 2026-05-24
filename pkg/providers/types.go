package providers

import (
	"context"
	"fmt"

	"github.com/laurenvil/Uno-QClaw/pkg/providers/protocoltypes"
)

type (
	ToolCall               = protocoltypes.ToolCall
	FunctionCall           = protocoltypes.FunctionCall
	LLMResponse            = protocoltypes.LLMResponse
	UsageInfo              = protocoltypes.UsageInfo
	Message                = protocoltypes.Message
	ToolDefinition         = protocoltypes.ToolDefinition
	ToolFunctionDefinition = protocoltypes.ToolFunctionDefinition
	ExtraContent           = protocoltypes.ExtraContent
	GoogleExtra            = protocoltypes.GoogleExtra
	ContentBlock           = protocoltypes.ContentBlock
	CacheControl           = protocoltypes.CacheControl
)

type LLMProvider interface {
	Chat(
		ctx context.Context,
		messages []Message,
		tools []ToolDefinition,
		model string,
		options map[string]any,
	) (*LLMResponse, error)
	GetDefaultModel() string
}

type StatefulProvider interface {
	LLMProvider
	Close()
}

// ThinkingCapable is an optional interface for providers that support
// extended thinking (e.g. Anthropic). Used by the agent loop to warn
// when thinking_level is configured but the active provider cannot use it.
type ThinkingCapable interface {
	SupportsThinking() bool
}

// Streamable is an optional interface for providers that can stream tokens
// as they are generated. onToken is called with each text fragment in order;
// the final assembled LLMResponse is returned when generation completes.
//
// Implementations may accept tools — for tool-aware streaming (OpenAI-style
// SSE with tool_calls deltas) — or refuse with ErrStreamingUnsupported when
// tools are passed to a text-only streaming backend. Callers treat that
// sentinel as a signal to fall back to the buffered Chat() path silently.
type Streamable interface {
	ChatStream(
		ctx context.Context,
		messages []Message,
		tools []ToolDefinition,
		model string,
		options map[string]any,
		onToken func(string),
	) (*LLMResponse, error)
}

// ErrStreamingUnsupported is re-exported from protocoltypes so callers can
// check for it without importing the leaf types package directly.
var ErrStreamingUnsupported = protocoltypes.ErrStreamingUnsupported

// FailoverReason classifies why an LLM request failed for fallback decisions.
type FailoverReason string

const (
	FailoverAuth       FailoverReason = "auth"
	FailoverRateLimit  FailoverReason = "rate_limit"
	FailoverBilling    FailoverReason = "billing"
	FailoverTimeout    FailoverReason = "timeout"
	FailoverFormat     FailoverReason = "format"
	FailoverOverloaded FailoverReason = "overloaded"
	FailoverUnknown    FailoverReason = "unknown"
)

// FailoverError wraps an LLM provider error with classification metadata.
type FailoverError struct {
	Reason   FailoverReason
	Provider string
	Model    string
	Status   int
	Wrapped  error
}

func (e *FailoverError) Error() string {
	return fmt.Sprintf("failover(%s): provider=%s model=%s status=%d: %v",
		e.Reason, e.Provider, e.Model, e.Status, e.Wrapped)
}

func (e *FailoverError) Unwrap() error {
	return e.Wrapped
}

// IsRetriable returns true if this error should trigger fallback to next candidate.
// Non-retriable: Format errors (bad request structure, image dimension/size).
func (e *FailoverError) IsRetriable() bool {
	return e.Reason != FailoverFormat
}

// ModelConfig holds primary model and fallback list.
type ModelConfig struct {
	Primary   string
	Fallbacks []string
}
