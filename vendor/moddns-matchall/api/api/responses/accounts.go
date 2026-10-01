package responses

import "time"

// DeletionCodeResponse represents the response when generating a deletion code
type DeletionCodeResponse struct {
	Code      string    `json:"code"`
	ExpiresAt time.Time `json:"expires_at"`
}
