package logging

import (
	"github.com/rs/zerolog"
)

// LoggerInterface defines the interface that all contextual loggers implement
// This interface mirrors the zerolog.Logger interface for easy compatibility
type LoggerInterface interface {
	// Event creation methods
	Trace() *zerolog.Event
	Debug() *zerolog.Event
	Info() *zerolog.Event
	Warn() *zerolog.Event
	Error() *zerolog.Event
	Fatal() *zerolog.Event
	Panic() *zerolog.Event
	Err(err error) *zerolog.Event

	// Configuration methods
	IsEnabled() bool
	Level(level zerolog.Level) *ContextLogger

	// Context methods
	WithField(key, value string) *ContextLogger
	WithFields(fields map[string]interface{}) *ContextLogger

	// Access methods
	Logger() zerolog.Logger
	Config() LoggingConfig
}

// Ensure ContextLogger implements LoggerInterface
var _ LoggerInterface = (*ContextLogger)(nil)

// FactoryInterface defines the interface for logger factories
type FactoryInterface interface {
	ForProfile(profileID string, logsEnabled bool) *ContextLogger
	ForSystem() *ContextLogger
	ForRequest(config LoggingConfig) *ContextLogger
	Disabled() *ContextLogger
	WithLevel(level zerolog.Level, profileID string, logsEnabled bool) *ContextLogger
}

// Ensure Factory implements FactoryInterface
var _ FactoryInterface = (*Factory)(nil)
