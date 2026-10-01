package middleware

import (
	sentryfiber "github.com/getsentry/sentry-go/fiber"
	"github.com/gofiber/fiber/v2"
)

// SentryFiber is a middleware that configures how fiber interacts with Sentry
func SentryFiber() fiber.Handler {
	return sentryfiber.New(sentryfiber.Options{
		Repanic:         true,
		WaitForDelivery: true,
	})
}
