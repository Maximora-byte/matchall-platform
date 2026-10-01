package service

import (
	"encoding/json"
	"os"

	"github.com/ivpn/dns/blocklists/model"
	"github.com/rs/zerolog/log"
)

// NewSources reads all blocklists sources from a JSON file
func NewSources(path string) ([]model.BlocklistMetadata, error) {
	log.Debug().Str("path", path).Msg("Reading JSON blocklist source file")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	sources := make([]model.BlocklistMetadata, 0)
	if err := json.Unmarshal(data, &sources); err != nil {
		return nil, err
	}
	return sources, nil
}
