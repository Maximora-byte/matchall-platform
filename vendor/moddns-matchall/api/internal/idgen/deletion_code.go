package idgen

import (
	"crypto/rand"
	"strings"
)

const (
	deletionCodeLength = 8
	deletionCodeChars  = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)

// DeletionCodeGenerator generates random deletion codes
type DeletionCodeGenerator struct{}

// NewDeletionCodeGenerator creates a new DeletionCodeGenerator instance
func NewDeletionCodeGenerator() (*DeletionCodeGenerator, error) {
	return &DeletionCodeGenerator{}, nil
}

// Generate creates a random deletion code (e.g., "ABC123XY")
func (g *DeletionCodeGenerator) Generate() (string, error) {
	bytes := make([]byte, deletionCodeLength)
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}

	var result strings.Builder
	for i := 0; i < deletionCodeLength; i++ {
		result.WriteByte(deletionCodeChars[bytes[i]%byte(len(deletionCodeChars))])
	}

	return result.String(), nil
}
