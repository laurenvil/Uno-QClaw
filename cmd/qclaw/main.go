// QClaw - On-device agentic AI assistant for Arduino Uno Q
// Forked from PicoClaw: https://github.com/laurenvil/Uno-QClaw
// License: MIT
//
// Copyright (c) 2026 QClaw contributors

package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/laurenvil/Uno-QClaw/cmd/qclaw/internal"
	"github.com/laurenvil/Uno-QClaw/cmd/qclaw/internal/agent"
	"github.com/laurenvil/Uno-QClaw/cmd/qclaw/internal/auth"
	"github.com/laurenvil/Uno-QClaw/cmd/qclaw/internal/cron"
	"github.com/laurenvil/Uno-QClaw/cmd/qclaw/internal/gateway"
	"github.com/laurenvil/Uno-QClaw/cmd/qclaw/internal/migrate"
	"github.com/laurenvil/Uno-QClaw/cmd/qclaw/internal/model"
	"github.com/laurenvil/Uno-QClaw/cmd/qclaw/internal/onboard"
	"github.com/laurenvil/Uno-QClaw/cmd/qclaw/internal/skills"
	"github.com/laurenvil/Uno-QClaw/cmd/qclaw/internal/status"
	"github.com/laurenvil/Uno-QClaw/cmd/qclaw/internal/version"
	"github.com/laurenvil/Uno-QClaw/pkg/config"
)

func NewQClawCommand() *cobra.Command {
	short := fmt.Sprintf("%s QClaw - On-Device AI for Arduino Uno Q v%s\n\n", internal.Logo, config.GetVersion())

	cmd := &cobra.Command{
		Use:     "qclaw",
		Short:   short,
		Example: "qclaw version",
	}

	cmd.AddCommand(
		onboard.NewOnboardCommand(),
		agent.NewAgentCommand(),
		auth.NewAuthCommand(),
		gateway.NewGatewayCommand(),
		status.NewStatusCommand(),
		cron.NewCronCommand(),
		migrate.NewMigrateCommand(),
		skills.NewSkillsCommand(),
		model.NewModelCommand(),
		version.NewVersionCommand(),
	)

	return cmd
}

const (
	colorBlue = "\033[1;38;2;62;93;185m"
	colorRed  = "\033[1;38;2;213;70;70m"
	banner    = "\r\n" +
		colorBlue + "██╗   ██╗ ███╗   ██╗  ██████╗   ██████╗ " + colorRed + " ██████╗██╗      █████╗ ██╗    ██╗\n" +
		colorBlue + "██║   ██║ ████╗  ██║ ██╔═══██╗ ██╔═══██╗" + colorRed + "██╔════╝██║     ██╔══██╗██║    ██║\n" +
		colorBlue + "██║   ██║ ██╔██╗ ██║ ██║   ██║ ██║   ██║" + colorRed + "██║     ██║     ███████║██║ █╗ ██║\n" +
		colorBlue + "██║   ██║ ██║╚██╗██║ ██║   ██║ ██║▄▄ ██║" + colorRed + "██║     ██║     ██╔══██║██║███╗██║\n" +
		colorBlue + "╚██████╔╝ ██║ ╚████║ ╚██████╔╝ ╚██████╔╝" + colorRed + "╚██████╗███████╗██║  ██║╚███╔███╔╝\n" +
		colorBlue + " ╚═════╝  ╚═╝  ╚═══╝  ╚═════╝   ╚══▀▀═╝ " + colorRed + " ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝\n " +
		"\033[0m\r\n"
)

func main() {
	fmt.Printf("%s", banner)
	cmd := NewQClawCommand()
	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}
