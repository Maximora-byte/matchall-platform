package logging_test

import (
	"fmt"

	"github.com/ivpn/dns/libs/logging"
	"github.com/rs/zerolog"
)

// Example: Basic usage of contextual logging
func ExampleContextLogger_basic() {
	// Create a logger for a profile with logging enabled
	logger := logging.ForProfile("user123", true)

	logger.Info().Msg("User performed an action")
	logger.Debug().Str("action", "dns_query").Msg("Debug information")

	// Create a logger for a profile with logging disabled
	disabledLogger := logging.ForProfile("user456", false)

	// This will not produce any output
	disabledLogger.Info().Msg("This message will be discarded")
}

// Example: Using factory for different scenarios
func ExampleFactory() {
	factory := logging.NewFactory(zerolog.DebugLevel)

	// System operations (always logged)
	systemLogger := factory.ForSystem()
	systemLogger.Info().Msg("System startup")

	// Profile-specific operations
	profileLogger := factory.ForProfile("profile123", true)
	profileLogger.Debug().Str("domain", "example.com").Msg("DNS query processed")

	// Disabled logging for privacy-sensitive profiles
	privateLogger := factory.ForProfile("private-profile", false)
	privateLogger.Info().Msg("This won't be logged")

	// Custom configuration
	customLogger := factory.ForRequest(logging.LoggingConfig{
		Enabled:   true,
		Level:     zerolog.ErrorLevel,
		ProfileID: "critical-profile",
	})
	customLogger.Error().Msg("Critical error occurred")
}

// Example_serviceIntegration shows how a service would typically use the contextual logger
func Example_serviceIntegration() {
	// This shows how a service would typically use the contextual logger

	type DNSService struct {
		loggerFactory *logging.Factory
	}

	newDNSService := func() *DNSService {
		return &DNSService{
			loggerFactory: logging.NewDefaultFactory(),
		}
	}

	processRequest := func(s *DNSService, profileID string, logsEnabled bool, domain string) {
		// Create profile-aware logger
		logger := s.loggerFactory.ForProfile(profileID, logsEnabled)

		logger.Info().
			Str("domain", domain).
			Msg("Processing DNS request")

		// Detailed debug information (will only log if profile allows it)
		logger.Debug().
			Str("action", "cache_lookup").
			Msg("Checking cache for domain")

		// Error logging (respects profile settings)
		if domain == "error.com" {
			logger.Error().
				Str("domain", domain).
				Msg("Failed to resolve domain")
		}

		logger.Info().Msg("Request processed successfully")
	}

	// Usage
	service := newDNSService()

	// This will log everything
	processRequest(service, "user1", true, "example.com")

	// This will log nothing
	processRequest(service, "user2", false, "private.com")
}

// Example: Adding contextual fields
func ExampleContextLogger_WithFields() {
	logger := logging.ForProfile("user123", true)

	// Add single field
	requestLogger := logger.WithField("request_id", "req-456")
	requestLogger.Info().Msg("Processing request")

	// Add multiple fields
	enrichedLogger := logger.WithFields(map[string]interface{}{
		"user_agent": "DNS-Client/1.0",
		"ip_address": "192.168.1.100",
		"timestamp":  1234567890,
		"encrypted":  true,
	})
	enrichedLogger.Info().Msg("Request with full context")
}

// Example_levels demonstrates different log levels
func Example_levels() {
	logger := logging.ForProfile("user123", true)

	// Different severity levels
	logger.Trace().Msg("Detailed tracing information")
	logger.Debug().Msg("Debug information for developers")
	logger.Info().Msg("General information")
	logger.Warn().Msg("Warning message")
	logger.Error().Msg("Error occurred")

	// Create logger with specific level
	errorOnlyLogger := logger.Level(zerolog.ErrorLevel)
	errorOnlyLogger.Info().Msg("This won't be logged")
	errorOnlyLogger.Error().Msg("This will be logged")
}

// Example_migration shows integration with existing code patterns
func Example_migration() {
	// Before: Direct zerolog usage
	// log.Info().Str("profile_id", profileID).Msg("Processing request")

	// After: Using contextual logger
	profileID := "user123"
	logsEnabled := true // This would come from profile settings

	logger := logging.ForProfile(profileID, logsEnabled)
	logger.Info().Msg("Processing request") // profile_id is automatically included
}

// Example_errorHandling demonstrates error logging patterns
func Example_errorHandling() {
	logger := logging.ForProfile("user123", true)

	// Log errors with context
	err := fmt.Errorf("connection failed")
	logger.Err(err).
		Str("server", "dns.example.com").
		Int("port", 53).
		Msg("DNS server connection failed")

	// Conditional logging based on profile settings
	if logger.IsEnabled() {
		// Only do expensive operations if logging is enabled
		complexData := map[string]interface{}{
			"computed_value": expensiveComputation(),
		}
		logger.Debug().Interface("data", complexData).Msg("Complex debug info")
	}
}

func expensiveComputation() string {
	return "expensive result"
}

func init() {
	// Configure zerolog for examples (suppress output in tests)
	zerolog.SetGlobalLevel(zerolog.Disabled)
}
