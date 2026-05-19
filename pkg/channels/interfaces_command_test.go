package channels

import (
	"context"
	"testing"

	"github.com/laurenvil/Uno-QClaw/pkg/commands"
)

type mockRegistrar struct{}

func (mockRegistrar) RegisterCommands(context.Context, []commands.Definition) error { return nil }

func TestCommandRegistrarCapable_Compiles(t *testing.T) {
	var _ CommandRegistrarCapable = mockRegistrar{}
}
