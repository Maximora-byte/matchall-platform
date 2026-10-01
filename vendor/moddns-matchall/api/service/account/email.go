package account

import (
	"github.com/ivpn/dns/api/model"
	"github.com/rs/zerolog/log"
)

// Email categories used for suppression logic
const (
	EmailCategoryWelcome         = "welcome"
	EmailCategoryVerificationOTP = "email_verification_otp"
	EmailCategoryPasswordReset   = "password_reset"
	EmailCategorySecurityAlert   = "security_alert"
)

// sendEmailCategory applies suppression rules before invoking the provided send function.
func (a *AccountService) sendEmailCategory(acc *model.Account, category string, send func() error) error {
	// Allowed pre-verification categories: welcome, verification OTP
	if !acc.EmailVerified && category != EmailCategoryWelcome && category != EmailCategoryVerificationOTP {
		log.Info().Str("account", acc.ID.Hex()).Str("category", category).Msg("email suppressed: unverified")
		return ErrEmailSuppressed
	}
	return send()
}
