package configstore

import (
	"errors"
	"os"
	"path/filepath"

	qclawconfig "github.com/laurenvil/Uno-QClaw/pkg/config"
)

const (
	configDirName  = ".qclaw"
	configFileName = "config.json"
)

func ConfigPath() (string, error) {
	dir, err := ConfigDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, configFileName), nil
}

func ConfigDir() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, configDirName), nil
}

func Load() (*qclawconfig.Config, error) {
	path, err := ConfigPath()
	if err != nil {
		return nil, err
	}
	return qclawconfig.LoadConfig(path)
}

func Save(cfg *qclawconfig.Config) error {
	if cfg == nil {
		return errors.New("config is nil")
	}
	path, err := ConfigPath()
	if err != nil {
		return err
	}
	return qclawconfig.SaveConfig(path, cfg)
}
