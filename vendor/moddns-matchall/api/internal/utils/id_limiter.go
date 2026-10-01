package utils

import (
	"context"
	"strconv"
	"time"

	"github.com/rs/zerolog/log"
)

type Cache interface {
	Get(context.Context, string) (string, error)
	Incr(context.Context, string, time.Duration) (int64, error)
}

type IDLimiter struct {
	ID    string
	Label string
	Max   int
	Exp   time.Duration
	Cache Cache
}

func (l *IDLimiter) Tick() error {
	key := l.Label + ":" + l.ID
	_, err := l.Cache.Incr(context.Background(), key, l.Exp)
	if err != nil {
		log.Error().Err(err).Msg("error incrementing failed attempts")
		return err
	}
	return nil
}

func (l *IDLimiter) IsAllowed() bool {
	failedAttempts, err := l.Cache.Get(context.Background(), l.Label+":"+l.ID)
	if err != nil {
		failedAttempts = "0"
	}
	failedAttemptsInt, err := strconv.Atoi(failedAttempts)
	if err != nil {
		failedAttemptsInt = 0
	}
	if failedAttemptsInt > l.Max {
		return false
	}

	return true
}
