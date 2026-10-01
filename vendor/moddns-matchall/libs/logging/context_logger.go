package logging

import (
	"io"

	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
)

// LoggingConfig holds configuration for contextual logging
type LoggingConfig struct {
	Enabled      bool          `json:"enabled"`
	Level        zerolog.Level `json:"level"`
	ProfileID    string        `json:"profile_id,omitempty"`
	LogDomains   bool          `json:"log_domains"`
	LogClientIPs bool          `json:"log_client_ips"`
}

// ContextLogger provides profile-aware logging functionality
type ContextLogger struct {
	config LoggingConfig
	logger zerolog.Logger
}

// NewContextLogger creates a new contextual logger with the given configuration
func NewContextLogger(config LoggingConfig) *ContextLogger {
	var logger zerolog.Logger

	if !config.Enabled {
		// Completely disable logging by discarding all output
		logger = zerolog.New(io.Discard).Level(zerolog.Disabled)
	} else {
		// Create logger with optional profile context
		if config.ProfileID != "" {
			logger = log.With().Str("profile_id", config.ProfileID).Logger()
		} else {
			logger = log.Logger
		}

		// Set the logging level
		logger = logger.Level(config.Level)
	}

	return &ContextLogger{
		config: config,
		logger: logger,
	}
}

// NewDisabledLogger creates a logger that discards all output
func NewDisabledLogger() *ContextLogger {
	return NewContextLogger(LoggingConfig{
		Enabled: false,
		Level:   zerolog.Disabled,
	})
}

// NewEnabledLogger creates a logger with normal output for the given profile
func NewEnabledLogger(profileID string, level zerolog.Level) *ContextLogger {
	return NewContextLogger(LoggingConfig{
		Enabled:   true,
		Level:     level,
		ProfileID: profileID,
	})
}

// Logger returns the underlying zerolog.Logger instance
func (cl *ContextLogger) Logger() zerolog.Logger {
	return cl.logger
}

// Config returns the logging configuration
func (cl *ContextLogger) Config() LoggingConfig {
	return cl.config
}

// IsEnabled returns whether logging is enabled for this context
func (cl *ContextLogger) IsEnabled() bool {
	return cl.config.Enabled
}

// WithField creates a new logger with an additional field
func (cl *ContextLogger) WithField(key, value string) *ContextLogger {
	newLogger := cl.logger.With().Str(key, value).Logger()
	return &ContextLogger{
		config: cl.config,
		logger: newLogger,
	}
}

// WithFields creates a new logger with additional fields
func (cl *ContextLogger) WithFields(fields map[string]any) *ContextLogger {
	loggerCtx := cl.logger.With()

	for key, value := range fields {
		switch v := value.(type) {
		case string:
			loggerCtx = loggerCtx.Str(key, v)
		case int:
			loggerCtx = loggerCtx.Int(key, v)
		case int64:
			loggerCtx = loggerCtx.Int64(key, v)
		case bool:
			loggerCtx = loggerCtx.Bool(key, v)
		case error:
			loggerCtx = loggerCtx.AnErr(key, v)
		default:
			loggerCtx = loggerCtx.Interface(key, v)
		}
	}

	return &ContextLogger{
		config: cl.config,
		logger: loggerCtx.Logger(),
	}
}

// Trace starts a new message with trace level
func (cl *ContextLogger) Trace() *zerolog.Event {
	return cl.logger.Trace()
}

// Debug starts a new message with debug level
func (cl *ContextLogger) Debug() *zerolog.Event {
	return cl.logger.Debug()
}

// Info starts a new message with info level
func (cl *ContextLogger) Info() *zerolog.Event {
	return cl.logger.Info()
}

// Warn starts a new message with warn level
func (cl *ContextLogger) Warn() *zerolog.Event {
	return cl.logger.Warn()
}

// Error starts a new message with error level
func (cl *ContextLogger) Error() *zerolog.Event {
	return cl.logger.Error()
}

// Fatal starts a new message with fatal level
func (cl *ContextLogger) Fatal() *zerolog.Event {
	return cl.logger.Fatal()
}

// Panic starts a new message with panic level
func (cl *ContextLogger) Panic() *zerolog.Event {
	return cl.logger.Panic()
}

// Err starts a new message with error level with err as a field if not nil
func (cl *ContextLogger) Err(err error) *zerolog.Event {
	return cl.logger.Err(err)
}

// Level creates a child logger with the minimum accepted level set to level
func (cl *ContextLogger) Level(level zerolog.Level) *ContextLogger {
	return &ContextLogger{
		config: LoggingConfig{
			Enabled:      cl.config.Enabled,
			Level:        level,
			ProfileID:    cl.config.ProfileID,
			LogDomains:   cl.config.LogDomains,   // preserve domain logging flag when changing level
			LogClientIPs: cl.config.LogClientIPs, // preserve client IP logging flag
		},
		logger: cl.logger.Level(level),
	}
}
