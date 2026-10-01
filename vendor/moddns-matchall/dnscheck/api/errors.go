package api

import (
	"github.com/gofiber/fiber/v2"
	"github.com/rs/zerolog/log"
)

const (
	ErrFailedToGetQueryData    = "Failed to get query data"
	ErrEntryNotFound           = "Entry not found"
	ErrFailedToUnmarshalRecord = "Failed to unmarshal record"
	ErrInvalidHostHeader       = "Invalid host header"
)

const (
	StatusDisconnected = "disconnected"
)

type ErrorResponse struct {
	Error       bool
	FailedField string
	Tag         string
	Value       any
}

type ErrResponse struct {
	Error   string `json:"error"`
	Details string `json:"details,omitempty"`
}

func HandleError(c *fiber.Ctx, err error, errMsg string) error {
	switch err.Error() {
	case ErrEntryNotFound:
		log.Debug().Err(err).Msg(errMsg)
		return c.Status(404).JSON(ErrResponse{
			Error: StatusDisconnected,
		})
	default:
		log.Error().Err(err).Msg(errMsg)
		return c.Status(500).JSON(ErrResponse{
			Error: errMsg,
		})
	}
}
