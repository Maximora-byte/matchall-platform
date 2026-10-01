package model

import (
	"crypto/rand"
	"encoding/base64"
	"time"

	"github.com/go-webauthn/webauthn/protocol"
	"github.com/go-webauthn/webauthn/webauthn"
	"go.mongodb.org/mongo-driver/bson/primitive"
)

// Credential represents a WebAuthn credential stored in the database
type Credential struct {
	ID                 primitive.ObjectID `json:"id" bson:"_id,omitempty"`
	CredentialID       []byte             `json:"-" bson:"credential_id"`
	CredentialIDString string             `json:"-" bson:"credential_id_string"`
	PublicKey          []byte             `json:"-" bson:"public_key"`
	AttestationType    string             `json:"-" bson:"attestation_type"`
	Transport          []string           `json:"-" bson:"transport"`
	Flags              CredentialFlags    `json:"-" bson:"flags"`
	Authenticator      Authenticator      `json:"-" bson:"authenticator"`
	AccountID          primitive.ObjectID `json:"-" bson:"account_id"`
	CreatedAt          time.Time          `json:"created_at" bson:"created_at"`
	UpdatedAt          time.Time          `json:"-" bson:"updated_at"`
	Name               string             `json:"-" bson:"name,omitempty"`
}

// CredentialFlags represents the flags of a WebAuthn credential
type CredentialFlags struct {
	UserPresent    bool `json:"user_present" bson:"user_present"`
	UserVerified   bool `json:"user_verified" bson:"user_verified"`
	BackupEligible bool `json:"backup_eligible" bson:"backup_eligible"`
	BackupState    bool `json:"backup_state" bson:"backup_state"`
}

// Authenticator represents the authenticator that created the credential
type Authenticator struct {
	AAGUID       []byte `json:"aaguid" bson:"aaguid"`
	SignCount    uint32 `json:"sign_count" bson:"sign_count"`
	CloneWarning bool   `json:"clone_warning" bson:"clone_warning"`
	Attachment   string `json:"attachment" bson:"attachment"`
}

// WebAuthnSession represents a temporary WebAuthn session
type WebAuthnSession struct {
	ID          primitive.ObjectID   `json:"id" bson:"_id,omitempty"`
	SessionData webauthn.SessionData `json:"session_data" bson:"session_data"`
	Token       string               `json:"token" bson:"token"`
	AccountID   primitive.ObjectID   `json:"account_id" bson:"account_id"`
	CreatedAt   time.Time            `json:"created_at" bson:"created_at"`
	ExpiresAt   time.Time            `json:"expires_at" bson:"expires_at"`
}

// ToWebAuthnCredential converts the database credential to WebAuthn credential
func (c *Credential) ToWebAuthnCredential() webauthn.Credential {
	// Convert string slice to protocol.AuthenticatorTransport slice
	transports := make([]protocol.AuthenticatorTransport, len(c.Transport))
	for i, t := range c.Transport {
		transports[i] = protocol.AuthenticatorTransport(t)
	}

	return webauthn.Credential{
		ID:              c.CredentialID,
		PublicKey:       c.PublicKey,
		AttestationType: c.AttestationType,
		Transport:       transports,
		Flags: webauthn.CredentialFlags{
			UserPresent:    c.Flags.UserPresent,
			UserVerified:   c.Flags.UserVerified,
			BackupEligible: c.Flags.BackupEligible,
			BackupState:    c.Flags.BackupState,
		},
		Authenticator: webauthn.Authenticator{
			AAGUID:       c.Authenticator.AAGUID,
			SignCount:    c.Authenticator.SignCount,
			CloneWarning: c.Authenticator.CloneWarning,
			Attachment:   protocol.AuthenticatorAttachment(c.Authenticator.Attachment),
		},
	}
}

// NewCredentialFromWebAuthn creates a new credential from WebAuthn credential
func NewCredentialFromWebAuthn(cred webauthn.Credential, accountID primitive.ObjectID) *Credential {
	// Convert protocol.AuthenticatorTransport slice to string slice
	transports := make([]string, len(cred.Transport))
	for i, t := range cred.Transport {
		transports[i] = string(t)
	}

	return &Credential{
		ID:                 primitive.NewObjectID(),
		CredentialID:       cred.ID,
		CredentialIDString: base64.StdEncoding.EncodeToString(cred.ID),
		PublicKey:          cred.PublicKey,
		AttestationType:    cred.AttestationType,
		Transport:          transports,
		Flags: CredentialFlags{
			UserPresent:    cred.Flags.UserPresent,
			UserVerified:   cred.Flags.UserVerified,
			BackupEligible: cred.Flags.BackupEligible,
			BackupState:    cred.Flags.BackupState,
		},
		Authenticator: Authenticator{
			AAGUID:       cred.Authenticator.AAGUID,
			SignCount:    cred.Authenticator.SignCount,
			CloneWarning: cred.Authenticator.CloneWarning,
			Attachment:   string(cred.Authenticator.Attachment),
		},
		AccountID: accountID,
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}
}

// NewWebAuthnSession creates a new WebAuthn session
func NewWebAuthnSession(sessionData webauthn.SessionData, token string, accountID primitive.ObjectID, duration time.Duration) *WebAuthnSession {
	now := time.Now()
	return &WebAuthnSession{
		ID:          primitive.NewObjectID(),
		SessionData: sessionData,
		Token:       token,
		AccountID:   accountID,
		CreatedAt:   now,
		ExpiresAt:   now.Add(duration),
	}
}

// GenerateRandomString generates a random string of specified length
func GenerateRandomString(length int) (string, error) {
	const charset = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	b := make([]byte, length)
	for i := range b {
		randomByte := make([]byte, 1)
		_, err := rand.Read(randomByte)
		if err != nil {
			return "", err
		}
		b[i] = charset[randomByte[0]%byte(len(charset))]
	}
	return string(b), nil
}
