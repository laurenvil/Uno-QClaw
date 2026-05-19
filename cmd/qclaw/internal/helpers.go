package internal

import (
	"os"
	"path/filepath"

	"github.com/laurenvil/Uno-QClaw/pkg/config"
)

const Logo = "🧘"

// GetQClawHome returns the qclaw home directory.
// Priority: $QCLAW_HOME > ~/.qclaw
func GetQClawHome() string {
	if home := os.Getenv("QCLAW_HOME"); home != "" {
		return home
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".qclaw")
}

func GetConfigPath() string {
	if configPath := os.Getenv("QCLAW_CONFIG"); configPath != "" {
		return configPath
	}
	return filepath.Join(GetQClawHome(), "config.json")
}

func LoadConfig() (*config.Config, error) {
	return config.LoadConfig(GetConfigPath())
}

// FormatVersion returns the version string with optional git commit
// Deprecated: Use pkg/config.FormatVersion instead
func FormatVersion() string {
	return config.FormatVersion()
}

// FormatBuildInfo returns build time and go version info
// Deprecated: Use pkg/config.FormatBuildInfo instead
func FormatBuildInfo() (string, string) {
	return config.FormatBuildInfo()
}

// GetVersion returns the version string
// Deprecated: Use pkg/config.GetVersion instead
func GetVersion() string {
	return config.GetVersion()
}
