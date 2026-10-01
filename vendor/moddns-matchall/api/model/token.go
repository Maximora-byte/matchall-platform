package model

import (
	"errors"
	"time"
)

var (
	ErrInvalidTokenType = errors.New("invalid token type")
)

type Token struct {
	Value     string    `json:"value" bson:"value"`
	Type      string    `json:"type" bson:"type"`
	ExpiresAt time.Time `json:"expires_at" bson:"expires_at"`
}
