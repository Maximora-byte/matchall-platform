package auth

import (
	"crypto/rand"
	"encoding/base64"
)

// GenerateSecureToken generates a secure token of a given length
func GenerateSecureToken(length int) (string, error) {
	b := make([]byte, length)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return base64.URLEncoding.EncodeToString(b), nil
}
