package middleware

import (
	"github.com/dnscheck/config"
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
)

func NewAPICORS(cfg config.APIConfig) fiber.Handler {
	return cors.New(cors.Config{
		AllowOrigins:     cfg.ApiAllowOrigin,
		AllowCredentials: false,
	})
}
