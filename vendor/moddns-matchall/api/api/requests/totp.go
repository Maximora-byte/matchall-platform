package requests

type TotpReq struct {
	OTP string `json:"otp" validate:"required,min=6,max=8"`
}
