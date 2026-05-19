package maixcam

import (
	"github.com/laurenvil/Uno-QClaw/pkg/bus"
	"github.com/laurenvil/Uno-QClaw/pkg/channels"
	"github.com/laurenvil/Uno-QClaw/pkg/config"
)

func init() {
	channels.RegisterFactory("maixcam", func(cfg *config.Config, b *bus.MessageBus) (channels.Channel, error) {
		return NewMaixCamChannel(cfg.Channels.MaixCam, b)
	})
}
