package deviceid

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNormalize(t *testing.T) {
	cases := []struct {
		name string
		in   string
		out  string
	}{
		{"empty", "", ""},
		{"allowed chars pass", "Abc 123-XY", "Abc 123-XY"},
		{"disallowed stripped", "My_Device!*?", "MyDevice"},
		{"spaces preserved", "My Phone Name", "My Phone Name"},
		{"apostrophe stripped", "Bob's Phone", "Bobs Phone"},
		// Truncation case: input length > MaxLength (36) should be truncated to first 36 allowed chars
		{"truncate", "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789EXTRA", "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"},
	}
	for _, tc := range cases {
		tt := tc
		if len(tt.out) > MaxLength { // safety for changes
			panic("expected output exceeds MaxLength constant")
		}
		if len(tt.out) > 0 && len(tt.out) <= MaxLength && len(tt.in) > MaxLength && tt.out == tt.in {
			panic("truncate test not effective: adjust input")
		}
		t.Run(tt.name, func(t *testing.T) {
			got := Normalize(tt.in)
			assert.Equal(t, tt.out, got)
			if len(got) > MaxLength {
				t.Fatalf("output length %d exceeds MaxLength %d", len(got), MaxLength)
			}
		})
	}
}

func TestEncodeDecodeLabel(t *testing.T) {
	cases := []struct {
		name    string
		logical string
		label   string
	}{
		{"empty", "", ""},
		{"no space", "DeviceA", "DeviceA"},
		{"single space", "My Phone", "My--Phone"},
		{"multiple spaces", "Living Room Router", "Living--Room--Router"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			enc := EncodeLabel(tc.logical)
			assert.Equal(t, tc.label, enc)
			dec := DecodeLabel(enc)
			assert.Equal(t, tc.logical, dec)
		})
	}
}

func TestSanitizeForDNS(t *testing.T) {
	cases := []struct {
		name string
		in   string
		out  string
	}{
		{"empty", "", ""},
		{"already label form", "My--Phone", EncodeLabel("My Phone")},
		{"needs normalization", "My__Phone!!!", EncodeLabel("MyPhone")},
		{"apostrophe removed", "Bob's--Phone", EncodeLabel("Bobs Phone")},
		{"truncate after decode", EncodeLabel("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789EXTRA"), EncodeLabel("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")},
		{"no truncate previously long", EncodeLabel("ThisDeviceNameIsWayTooLongForLimit"), EncodeLabel("ThisDeviceNameIsWayTooLongForLimit")},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := SanitizeForDNS(tc.in)
			assert.Equal(t, tc.out, got)
		})
	}
}

func TestRoundTripLogicalToLabel(t *testing.T) {
	inputs := []string{"", "A", "My Phone", "Edge  Case  With  Double  Spaces"}
	for _, in := range inputs {
		label := EncodeLabel(Normalize(in))
		logical := DecodeLabel(label)
		// After decode we have logical with spaces, but must still equal Normalize(in) except for multiple-space collapse? We don't collapse spaces; so compare normalization then spaces pattern.
		assert.Equal(t, Normalize(in), Normalize(logical))
	}
}

func TestMaxLengthConstant(t *testing.T) {
	// Ensure MaxLength matches expectations used elsewhere (updated to 36)
	require.Equal(t, 36, MaxLength)
}

func TestEncodeDecodeURL(t *testing.T) {
	tests := []struct {
		name     string
		logical  string
		expected string
	}{
		{"empty", "", ""},
		{"no spaces", "iPhone", "iPhone"},
		{"spaces", "My Phone", "My%20Phone"},
		{"multiple spaces", "John s iPhone 15", "John%20s%20iPhone%2015"},
		{"spaces and special chars", "Test Device #1", "Test%20Device%20%231"},
		{"unicode", "João's Phone", "Jo%C3%A3o%27s%20Phone"},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			// Test encoding
			enc := EncodeURL(tc.logical)
			require.Equal(t, tc.expected, enc, "EncodeURL failed for input: %q", tc.logical)

			// Test round-trip decoding
			dec := DecodeURL(enc)
			require.Equal(t, tc.logical, dec, "DecodeURL failed for encoded: %q", enc)
		})
	}

	// Test decoding invalid URL encoding
	t.Run("invalid encoding", func(t *testing.T) {
		invalid := "bad%escape"
		decoded := DecodeURL(invalid)
		// Should return original string if decoding fails
		require.Equal(t, invalid, decoded)
	})
}
