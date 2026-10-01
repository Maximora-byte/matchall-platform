package logging

import (
	"github.com/rs/zerolog"
)

// Common log levels for convenience
const (
	LevelTrace    = zerolog.TraceLevel
	LevelDebug    = zerolog.DebugLevel
	LevelInfo     = zerolog.InfoLevel
	LevelWarn     = zerolog.WarnLevel
	LevelError    = zerolog.ErrorLevel
	LevelFatal    = zerolog.FatalLevel
	LevelPanic    = zerolog.PanicLevel
	LevelDisabled = zerolog.Disabled
)

// Profile-aware logging convenience functions
var (
	// DefaultFactory is the default logger factory instance
	DefaultFactory = NewDefaultFactory()
)

// ForProfile creates a logger for a specific profile using the default factory
func ForProfile(profileID string, logsEnabled bool) *ContextLogger {
	return DefaultFactory.ForProfile(profileID, logsEnabled)
}

// ForSystem creates a system logger using the default factory
func ForSystem() *ContextLogger {
	return DefaultFactory.ForSystem()
}

// Disabled creates a disabled logger using the default factory
func Disabled() *ContextLogger {
	return DefaultFactory.Disabled()
}

// WithLevel creates a logger with specific level using the default factory
func WithLevel(level zerolog.Level, profileID string, logsEnabled bool) *ContextLogger {
	return DefaultFactory.WithLevel(level, profileID, logsEnabled)
}

// SetDefaultLevel sets the default logging level for the default factory
func SetDefaultLevel(level zerolog.Level) {
	DefaultFactory = NewFactory(level)
}
