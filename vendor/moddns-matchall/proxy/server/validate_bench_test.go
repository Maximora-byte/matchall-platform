package server

import (
	"testing"
)

func BenchmarkSanitizeDeviceIdForDNS(b *testing.B) {
	testCases := []struct {
		name     string
		deviceId string
	}{
		{"clean", "laptop"},
		{"with_spaces", "my laptop"},
		{"with_special_chars", "my*laptop^"},
		{"complex", "John's iPhone 12 Pro Max!"},
	}

	for _, tc := range testCases {
		b.Run(tc.name, func(b *testing.B) {
			for i := 0; i < b.N; i++ {
				_ = SanitizeDeviceIdForDNS(tc.deviceId)
			}
		})
	}
}
