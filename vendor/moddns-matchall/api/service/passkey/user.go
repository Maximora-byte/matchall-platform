package passkey

import (
	"github.com/go-webauthn/webauthn/webauthn"
	"github.com/ivpn/dns/api/model"
)

// WebAuthnUser implements the webauthn.User interface
type WebAuthnUser struct {
	Account     *model.Account
	Credentials []webauthn.Credential
}

// WebAuthnID implements webauthn.User
func (u *WebAuthnUser) WebAuthnID() []byte {
	return u.Account.WebAuthnID()
}

// WebAuthnName implements webauthn.User
func (u *WebAuthnUser) WebAuthnName() string {
	return u.Account.WebAuthnName()
}

// WebAuthnDisplayName implements webauthn.User
func (u *WebAuthnUser) WebAuthnDisplayName() string {
	return u.Account.WebAuthnDisplayName()
}

// WebAuthnCredentials implements webauthn.User
func (u *WebAuthnUser) WebAuthnCredentials() []webauthn.Credential {
	return u.Credentials
}
