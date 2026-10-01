package logging

import (
	"testing"

	"github.com/rs/zerolog"
)

func TestDefaultFactory(t *testing.T) {
	if DefaultFactory == nil {
		t.Error("Expected DefaultFactory to be initialized")
	}

	if DefaultFactory.defaultLevel != zerolog.DebugLevel {
		t.Errorf("Expected DefaultFactory default level to be DebugLevel, got %v", DefaultFactory.defaultLevel)
	}
}

func TestForProfile(t *testing.T) {
	logger := ForProfile("test-profile", true)

	if !logger.IsEnabled() {
		t.Error("Expected profile logger to be enabled")
	}

	if logger.Config().ProfileID != "test-profile" {
		t.Errorf("Expected ProfileID to be 'test-profile', got '%s'", logger.Config().ProfileID)
	}
}

func TestForSystem(t *testing.T) {
	logger := ForSystem()

	if !logger.IsEnabled() {
		t.Error("Expected system logger to be enabled")
	}

	if logger.Config().ProfileID != "" {
		t.Errorf("Expected system logger ProfileID to be empty, got '%s'", logger.Config().ProfileID)
	}
}

func TestDisabled(t *testing.T) {
	logger := Disabled()

	if logger.IsEnabled() {
		t.Error("Expected disabled logger to be disabled")
	}
}

func TestWithLevel(t *testing.T) {
	logger := WithLevel(zerolog.ErrorLevel, "test-profile", true)

	if !logger.IsEnabled() {
		t.Error("Expected logger to be enabled")
	}

	if logger.Config().Level != zerolog.ErrorLevel {
		t.Errorf("Expected level to be ErrorLevel, got %v", logger.Config().Level)
	}

	if logger.Config().ProfileID != "test-profile" {
		t.Errorf("Expected ProfileID to be 'test-profile', got '%s'", logger.Config().ProfileID)
	}
}

func TestSetDefaultLevel(t *testing.T) {
	// Save original factory
	originalFactory := DefaultFactory
	defer func() {
		DefaultFactory = originalFactory
	}()

	// Test setting new default level
	SetDefaultLevel(zerolog.WarnLevel)

	if DefaultFactory.defaultLevel != zerolog.WarnLevel {
		t.Errorf("Expected DefaultFactory level to be WarnLevel after SetDefaultLevel, got %v", DefaultFactory.defaultLevel)
	}

	// Test that new loggers use the new default level
	logger := ForProfile("test", true)
	if logger.Config().Level != zerolog.WarnLevel {
		t.Errorf("Expected new logger to use WarnLevel, got %v", logger.Config().Level)
	}
}

func TestLevelConstants(t *testing.T) {
	// Test that our level constants match zerolog constants
	tests := []struct {
		ours    zerolog.Level
		zerolog zerolog.Level
		name    string
	}{
		{LevelTrace, zerolog.TraceLevel, "Trace"},
		{LevelDebug, zerolog.DebugLevel, "Debug"},
		{LevelInfo, zerolog.InfoLevel, "Info"},
		{LevelWarn, zerolog.WarnLevel, "Warn"},
		{LevelError, zerolog.ErrorLevel, "Error"},
		{LevelFatal, zerolog.FatalLevel, "Fatal"},
		{LevelPanic, zerolog.PanicLevel, "Panic"},
		{LevelDisabled, zerolog.Disabled, "Disabled"},
	}

	for _, test := range tests {
		if test.ours != test.zerolog {
			t.Errorf("Level constant mismatch for %s: expected %v, got %v", test.name, test.zerolog, test.ours)
		}
	}
}
