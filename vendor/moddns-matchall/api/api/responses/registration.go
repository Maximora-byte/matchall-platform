package responses

// RegistrationSuccessResponse represents a successful account registration response without exposing account details.
type RegistrationSuccessResponse struct {
	Message string `json:"message" example:"Account created successfully."`
}
