package model

import (
	"github.com/google/uuid"
)

type MobileConfig struct {
	ProfileId       string `json:"profile_id" validate:"required"`
	AdvancedOptions `json:"advanced_options"`
	// Following fields are not exposed to the user and used only internally
	PayloadIdentifier            uuid.UUID `json:"-"`
	ContentIdentifier            uuid.UUID `json:"-"`
	PayloadUUID                  uuid.UUID `json:"-"`
	ServerAddresses              []string  `json:"-"` // IP addresses of the DNS servers, needed for TLS encryption
	ServerDomain                 string    `json:"-"`
	DNSSettingsPayloadType       string    `json:"-"`
	DNSSettingsPayloadIdentifier string    `json:"-"`
	DNSSettingsPayloadUUID       uuid.UUID `json:"-"`
	// Optional normalized device identifier (logical form with spaces preserved).
	DeviceId string `json:"-"`
	// Derived fields for template rendering when DeviceId provided.
	DeviceLabelEncoded string `json:"-"` // spaces replaced with -- for label usage (SNI)
}

type AdvancedOptions struct {
	EncryptionType string `json:"encryption_type"`
	// ExcludedDomains          []string `json:"excluded_domains"` // unnecessary
	ExcludedWifiNetworks []string `json:"excluded_wifi_networks"`
	// PayloadRemovalDisallowed bool     `json:"payload_removal_disallowed"` // option not required now
	SignConfigurationProfile bool `json:"-"` // `json:"sign_configuration_profile"` // all config profiles are signed by default
}
