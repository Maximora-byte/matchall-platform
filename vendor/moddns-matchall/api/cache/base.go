package cache

import (
	"context"
	"time"
)

type CacheBase interface {
	Set(context.Context, string, any, time.Duration) error
	Get(context.Context, string) (string, error)
	Del(context.Context, string) error
	Incr(context.Context, string, time.Duration) (int64, error)
}
