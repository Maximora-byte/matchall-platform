package responses

import "time"

type WebAuthnReauthFinishResponse struct {
	ReauthToken string    `json:"reauth_token"`
	ExpiresAt   time.Time `json:"expires_at"`
}
