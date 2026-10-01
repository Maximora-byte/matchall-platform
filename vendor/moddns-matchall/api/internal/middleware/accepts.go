package middleware

import (
	"github.com/gofiber/fiber/v2"
	"github.com/rs/zerolog/log"
)

func NewAccepts(acceptedTypes ...string) fiber.Handler {
	return func(c *fiber.Ctx) error {
		accepted := c.Accepts(acceptedTypes...)
		if accepted == "" {
			log.Warn().Msg("Not Acceptable")
			return c.Status(fiber.StatusNotAcceptable).SendString("Not Acceptable")
		}
		return c.Next()
	}
}
