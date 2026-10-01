package logging

import (
	"testing"

	"github.com/rs/zerolog"
)

// BenchmarkEnabledLogger benchmarks logging when enabled
func BenchmarkEnabledLogger(b *testing.B) {
	logger := NewEnabledLogger("bench-profile", zerolog.InfoLevel)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		logger.Info().Str("key", "value").Int("iteration", i).Msg("benchmark message")
	}
}

// BenchmarkDisabledLogger benchmarks logging when disabled
func BenchmarkDisabledLogger(b *testing.B) {
	logger := NewDisabledLogger()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		logger.Info().Str("key", "value").Int("iteration", i).Msg("benchmark message")
	}
}

// BenchmarkDirectZerolog benchmarks direct zerolog usage for comparison
func BenchmarkDirectZerolog(b *testing.B) {
	logger := zerolog.New(nil).With().Str("profile_id", "bench-profile").Logger()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		logger.Info().Str("key", "value").Int("iteration", i).Msg("benchmark message")
	}
}

// BenchmarkLoggerCreation benchmarks the cost of creating loggers
func BenchmarkLoggerCreation(b *testing.B) {
	factory := NewDefaultFactory()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		logger := factory.ForProfile("bench-profile", true)
		_ = logger
	}
}

// BenchmarkDisabledLoggerCreation benchmarks the cost of creating disabled loggers
func BenchmarkDisabledLoggerCreation(b *testing.B) {
	factory := NewDefaultFactory()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		logger := factory.ForProfile("bench-profile", false)
		_ = logger
	}
}

// BenchmarkConditionalLogging benchmarks the common pattern of checking IsEnabled
func BenchmarkConditionalLogging(b *testing.B) {
	logger := NewDisabledLogger()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if logger.IsEnabled() {
			// This expensive operation won't run for disabled loggers
			expensiveData := make(map[string]interface{})
			expensiveData["computation"] = "expensive result"
			logger.Debug().Interface("data", expensiveData).Msg("expensive debug")
		}
	}
}

// BenchmarkWithFields benchmarks adding contextual fields
func BenchmarkWithFields_Enabled(b *testing.B) {
	logger := NewEnabledLogger("bench-profile", zerolog.InfoLevel)
	fields := map[string]interface{}{
		"request_id": "req-123",
		"user_id":    "user-456",
		"action":     "dns_query",
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		enrichedLogger := logger.WithFields(fields)
		enrichedLogger.Info().Msg("request processed")
	}
}

func BenchmarkWithFields_Disabled(b *testing.B) {
	logger := NewDisabledLogger()
	fields := map[string]interface{}{
		"request_id": "req-123",
		"user_id":    "user-456",
		"action":     "dns_query",
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		enrichedLogger := logger.WithFields(fields)
		enrichedLogger.Info().Msg("request processed")
	}
}
