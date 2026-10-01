package middleware

import (
	"github.com/gofiber/fiber/v2"
	"github.com/rs/zerolog/log"
)

func Recover() fiber.Handler {
	return func(c *fiber.Ctx) error {
		defer func() {
			if r := recover(); r != nil {
				// Log the actual panic for debugging
				log.Error().
					Interface("panic", r).
					Str("method", c.Method()).
					Str("path", c.Path()).
					Msg("Panic recovered")

				// Return generic error response
				if err := c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
					"error":   "Something went wrong. Please try again later.",
					"message": "Something went wrong. Please try again later.",
				}); err != nil {
					log.Error().Err(err).Msg("failed to write panic recovery response")
				}
			}
		}()
		return c.Next()
	}
}
