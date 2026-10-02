package cache

import (
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNewDirectClient_CommandTimeoutApplied(t *testing.T) {
	c, err := NewDirectClient(&Config{Address: "127.0.0.1:1", CommandTimeout: 750 * time.Millisecond})
	require.NoError(t, err)
	defer c.Close()

	opts := c.Options()
	assert.Equal(t, 750*time.Millisecond, opts.DialTimeout)
	assert.Equal(t, 750*time.Millisecond, opts.ReadTimeout)
	assert.Equal(t, 750*time.Millisecond, opts.WriteTimeout)
	assert.Equal(t, 1, opts.MaxRetries)
	assert.True(t, opts.ContextTimeoutEnabled)
}

func TestNewDirectClient_ZeroTimeoutKeepsClientDefaults(t *testing.T) {
	c, err := NewDirectClient(&Config{Address: "127.0.0.1:1"})
	require.NoError(t, err)
	defer c.Close()

	// Zero must leave the library defaults untouched, including when go-redis
	// changes those defaults between versions.
	baseline := redis.NewClient(&redis.Options{Addr: "127.0.0.1:1"})
	defer baseline.Close()
	defaults := baseline.Options()
	opts := c.Options()
	assert.Equal(t, defaults.DialTimeout, opts.DialTimeout)
	assert.Equal(t, defaults.ReadTimeout, opts.ReadTimeout)
	assert.Equal(t, defaults.WriteTimeout, opts.WriteTimeout)
	assert.Equal(t, defaults.MaxRetries, opts.MaxRetries)
	assert.Equal(t, defaults.ContextTimeoutEnabled, opts.ContextTimeoutEnabled)
}

func TestNewFailoverClient_CommandTimeoutApplied(t *testing.T) {
	c, err := NewFailoverClient(&Config{MasterName: "m", FailoverAddresses: []string{"127.0.0.1:1"}, CommandTimeout: 400 * time.Millisecond})
	require.NoError(t, err)
	defer c.Close()

	opts := c.Options()
	assert.Equal(t, 400*time.Millisecond, opts.DialTimeout)
	assert.Equal(t, 400*time.Millisecond, opts.ReadTimeout)
	assert.Equal(t, 400*time.Millisecond, opts.WriteTimeout)
	assert.Equal(t, 1, opts.MaxRetries)
	assert.True(t, opts.ContextTimeoutEnabled)
}
