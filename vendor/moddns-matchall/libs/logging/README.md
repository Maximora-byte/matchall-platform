# Contextual Logging Package

A profile-aware logging package that provides strict privacy controls for DNS service logging. This package allows complete disabling of application logs based on user profile preferences while maintaining zero performance overhead.

## Features

- **Profile-aware logging**: Automatically include or exclude profile context
- **Zero overhead when disabled**: Uses `io.Discard` for complete log suppression
- **Simple boolean-based configuration**: No complex dependencies or cache injection
- **Full zerolog compatibility**: Drop-in replacement for existing zerolog usage
- **Type-safe interfaces**: Well-defined interfaces for easy testing and mocking
- **Factory pattern**: Convenient logger creation for different scenarios

## Quick Start

```go
import "github.com/ivpn/dns/libs/logging"

// Create logger for a profile with logging enabled
logger := logging.ForProfile("user123", true)
logger.Info().Msg("User action logged")

// Create logger for a profile with logging disabled (produces no output)
disabledLogger := logging.ForProfile("user456", false)
disabledLogger.Info().Msg("This will be completely discarded")

// System operations (always logged)
systemLogger := logging.ForSystem()
systemLogger.Error().Msg("System error occurred")
```

## Core Components

### ContextLogger

The main logger type that wraps zerolog with profile-aware functionality:

```go
type ContextLogger struct {
    // Internal fields
}

// Configuration for the logger
type LoggingConfig struct {
    Enabled   bool          `json:"enabled"`
    Level     zerolog.Level `json:"level"`
    ProfileID string        `json:"profile_id,omitempty"`
}
```

### Factory

Provides convenient methods for creating loggers in different scenarios:

```go
factory := logging.NewDefaultFactory()

// Profile-specific logger
profileLogger := factory.ForProfile("profile123", logsEnabled)

// System logger (always enabled)
systemLogger := factory.ForSystem()

// Custom configuration
customLogger := factory.ForRequest(logging.LoggingConfig{
    Enabled:   true,
    Level:     zerolog.DebugLevel,
    ProfileID: "custom-profile",
})
```

## Usage Patterns

### Service Integration

```go
type DNSService struct {
    loggerFactory *logging.Factory
}

func NewDNSService() *DNSService {
    return &DNSService{
        loggerFactory: logging.NewDefaultFactory(),
    }
}

func (s *DNSService) ProcessRequest(profileID string, logsEnabled bool, domain string) {
    // Create profile-aware logger
    logger := s.loggerFactory.ForProfile(profileID, logsEnabled)
    
    logger.Info().Str("domain", domain).Msg("Processing DNS request")
    
    // This debug log will only appear if profile logging is enabled
    logger.Debug().Str("action", "cache_lookup").Msg("Checking cache")
    
    if err != nil {
        logger.Error().Err(err).Msg("Request failed")
    }
}
```

### Request Context Pattern

```go
// At request entry point, determine logging state once
func handleRequest(profileID string) {
    logsEnabled := getProfileLogsEnabled(profileID) // Your profile lookup logic
    
    // Create logger with determined state
    logger := logging.ForProfile(profileID, logsEnabled)
    
    // Pass logger through request context
    processRequest(logger, ...)
}

func processRequest(logger *logging.ContextLogger, ...) {
    logger.Info().Msg("Processing request")
    // Logger respects profile settings automatically
}
```

### Migration from Direct zerolog

```go
// Before
log.Info().Str("profile_id", profileID).Msg("Processing request")

// After
logger := logging.ForProfile(profileID, logsEnabled)
logger.Info().Msg("Processing request") // profile_id automatically included
```

## API Reference

### Package-level Functions

```go
// Create loggers using the default factory
ForProfile(profileID string, logsEnabled bool) *ContextLogger
ForSystem() *ContextLogger
Disabled() *ContextLogger
WithLevel(level zerolog.Level, profileID string, logsEnabled bool) *ContextLogger

// Configure default behavior
SetDefaultLevel(level zerolog.Level)
```

### ContextLogger Methods

```go
// Logging methods (same as zerolog)
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
```

### Factory Methods

```go
ForProfile(profileID string, logsEnabled bool) *ContextLogger
ForSystem() *ContextLogger
ForRequest(config LoggingConfig) *ContextLogger
Disabled() *ContextLogger
WithLevel(level zerolog.Level, profileID string, logsEnabled bool) *ContextLogger
```

## Performance Considerations

### Zero Overhead When Disabled

When logging is disabled for a profile, the logger uses `io.Discard` which provides true zero-allocation, zero-CPU logging:

```go
disabledLogger := logging.ForProfile("user", false)
disabledLogger.Info().Msg("This has zero performance impact")
```

### Efficient Profile Context

Profile IDs are added to the logger context once during creation, avoiding repeated string operations:

```go
logger := logging.ForProfile("user123", true)
logger.Info().Msg("message 1") // profile_id included
logger.Debug().Msg("message 2") // profile_id included
// No additional string operations per log call
```

## Best Practices

### 1. Determine Logging State Early

```go
// Good: Determine once at request boundary
logsEnabled := getProfileSettings(profileID)
logger := logging.ForProfile(profileID, logsEnabled)

// Avoid: Checking profile settings for every log call
```

### 2. Use Factory Pattern for Services

```go
type Service struct {
    loggerFactory *logging.Factory
}

func (s *Service) HandleRequest(profileID string, logsEnabled bool) {
    logger := s.loggerFactory.ForProfile(profileID, logsEnabled)
    // Use logger throughout request handling
}
```

### 3. Conditional Expensive Operations

```go
if logger.IsEnabled() {
    // Only do expensive computation if logging is enabled
    complexData := computeExpensiveDebugInfo()
    logger.Debug().Interface("debug_data", complexData).Msg("Debug info")
}
```

### 4. System vs Profile Logging

```go
// System operations - always logged
systemLogger := logging.ForSystem()
systemLogger.Error().Msg("System startup failed")

// User operations - respect profile settings
userLogger := logging.ForProfile(profileID, logsEnabled)
userLogger.Info().Msg("User action performed")
```

## Testing

The package includes comprehensive tests and examples:

```bash
go test ./libs/logging
go test ./libs/logging -run Example
```

## Integration Notes

- **No external dependencies**: Only depends on zerolog
- **No cache injection**: Simple boolean configuration
- **Thread-safe**: All operations are thread-safe
- **Memory efficient**: Minimal memory overhead
- **Zero allocation when disabled**: True zero-cost abstraction
