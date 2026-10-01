package errors

import "errors"

var (
	ErrAccountNotFound         = errors.New("account not found")
	ErrProfileNotFound         = errors.New("profile not found")
	ErrProfileSettingsNotFound = errors.New("profile settings not found")
	ErrCustomRuleNotFound      = errors.New("custom rule not found")
)
