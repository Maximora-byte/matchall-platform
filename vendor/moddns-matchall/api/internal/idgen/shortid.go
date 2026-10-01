package idgen

import (
	"fmt"

	"github.com/teris-io/shortid"
)

// ShortIdGenerator generates short ids
type ShortIdGenerator struct {
	sid *shortid.Shortid
}

// NewShortIdGenerator creates a new short id generator
func NewShortIdGenerator() (*ShortIdGenerator, error) {
	var seed uint64 = 2342

	sid, err := shortid.New(1, shortid.DefaultABC, seed)
	if err != nil {
		return nil, fmt.Errorf("failed to create shortid generator: %w", err)
	}
	return &ShortIdGenerator{
		sid: sid,
	}, nil
}

// Generate generates a new short id
func (gen *ShortIdGenerator) Generate() (string, error) {
	return gen.sid.Generate()
}
