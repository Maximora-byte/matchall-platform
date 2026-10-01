package deviceid

import (
	"net/url"
	"strings"
)

// MaxLength defines the maximum length of a normalized device identifier.
// Keep in sync with any proxy/server expectations and mobileconfig generation.
const MaxLength = 36

// Normalize keeps only allowed characters [A-Za-z0-9 -] and truncates to MaxLength.
// Returns logical form (spaces preserved).
func Normalize(raw string) string {
	if raw == "" {
		return ""
	}
	buf := make([]byte, 0, len(raw))
	for i := 0; i < len(raw); i++ {
		c := raw[i]
		switch {
		case c >= 'a' && c <= 'z', c >= 'A' && c <= 'Z', c >= '0' && c <= '9', c == ' ', c == '-':
			buf = append(buf, c)
		default:
			// skip
		}
	}
	if len(buf) > MaxLength {
		buf = buf[:MaxLength]
	}
	return string(buf)
}

// EncodeLabel converts logical spaces to "--" for DNS label/SNI usage.
func EncodeLabel(logical string) string {
	if logical == "" {
		return ""
	}
	return strings.ReplaceAll(logical, " ", "--")
}

// DecodeLabel reverses EncodeLabel ("--" -> space).
func DecodeLabel(label string) string {
	if label == "" {
		return ""
	}
	return strings.ReplaceAll(label, "--", " ")
}

// EncodeURL converts logical spaces to "%20" for URL path usage.
func EncodeURL(logical string) string {
	if logical == "" {
		return ""
	}
	return url.PathEscape(logical)
}

// DecodeURL reverses EncodeURL (URL-decodes back to logical form).
func DecodeURL(encoded string) string {
	if encoded == "" {
		return ""
	}
	decoded, err := url.PathUnescape(encoded)
	if err != nil {
		// If decoding fails, return original (may already be logical form)
		return encoded
	}
	return decoded
}

// SanitizeForDNS maintains backward compatibility for label forms coming from DNS label.
// It decodes label representation, normalizes, then re-encodes for label usage.
func SanitizeForDNS(device string) string {
	logical := DecodeLabel(device)
	logical = Normalize(logical)
	return EncodeLabel(logical)
}
