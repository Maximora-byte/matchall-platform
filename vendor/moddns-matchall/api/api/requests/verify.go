package requests

type VerifyEmailBody struct {
	Token string `json:"token" validate:"required"`
}
