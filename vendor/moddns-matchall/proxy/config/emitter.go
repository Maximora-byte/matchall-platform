package config

import (
	"errors"
	"os"

	"github.com/ivpn/dns/libs/store"
)

type EmitterConfig struct {
	Type       string
	SinkConfig SinkConfig
}

type SinkConfig any

func NewSinkConfig(sinkType string) (SinkConfig, error) {
	switch sinkType {
	case "mongodb":
		return store.Config{
			DbURI:    os.Getenv("EMITTER_SINK_DB_URI"),
			Name:     os.Getenv("EMITTER_SINK_DB_NAME"),
			Username: os.Getenv("EMITTER_SINK_DB_USERNAME"),
			Password: os.Getenv("EMITTER_SINK_DB_PASSWORD"),
			AuthSource: func() string {
				v := os.Getenv("EMITTER_SINK_DB_AUTH_SOURCE")
				if v == "" {
					return "dns"
				}
				return v
			}(),
		}, nil
	default:
		return nil, errors.New("unsupported sink type")
	}
}
