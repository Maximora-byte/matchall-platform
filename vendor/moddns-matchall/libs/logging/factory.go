package logging

import (
	"github.com/rs/zerolog"
)

// Factory provides convenient methods for creating loggers in different scenarios
type Factory struct {
	defaultLevel zerolog.Level
}

// NewFactory creates a new logger factory with the specified default level
func NewFactory(defaultLevel zerolog.Level) *Factory {
	return &Factory{
		defaultLevel: defaultLevel,
	}
}

// NewDefaultFactory creates a new logger factory with DEBUG level as default
func NewDefaultFactory() *Factory {
	return NewFactory(zerolog.DebugLevel)
}

// ForProfile creates a contextual logger for a specific profile
func (f *Factory) ForProfile(profileID string, logsEnabled bool) *ContextLogger {
	return NewContextLogger(LoggingConfig{
		Enabled:   logsEnabled,
		Level:     f.defaultLevel,
		ProfileID: profileID,
	})
}

// ForSystem creates a contextual logger for system operations (always enabled)
func (f *Factory) ForSystem() *ContextLogger {
	return NewContextLogger(LoggingConfig{
		Enabled: true,
		Level:   f.defaultLevel,
	})
}

// ForRequest creates a contextual logger for a request with custom configuration
func (f *Factory) ForRequest(config LoggingConfig) *ContextLogger {
	// Use default level if not specified
	if config.Level == 0 {
		config.Level = f.defaultLevel
	}
	return NewContextLogger(config)
}

// Disabled creates a logger that discards all output
func (f *Factory) Disabled() *ContextLogger {
	return NewDisabledLogger()
}

// WithLevel creates a contextual logger with a specific level
func (f *Factory) WithLevel(level zerolog.Level, profileID string, logsEnabled bool) *ContextLogger {
	return NewContextLogger(LoggingConfig{
		Enabled:   logsEnabled,
		Level:     level,
		ProfileID: profileID,
	})
}
