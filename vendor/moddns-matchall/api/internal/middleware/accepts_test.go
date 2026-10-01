package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gofiber/fiber/v2"
	"github.com/stretchr/testify/assert"
)

func TestAcceptsMiddleware(t *testing.T) {
	tests := []struct {
		name           string
		acceptHeader   string
		expectedStatus int
	}{
		{
			name:           "AllowsMatchingAcceptHeader",
			acceptHeader:   "application/json",
			expectedStatus: fiber.StatusOK,
		},
		{
			name:           "RejectsNoAcceptHeader",
			acceptHeader:   "",
			expectedStatus: fiber.StatusOK,
		},
		{
			name:           "WithMalformedAcceptHeader",
			acceptHeader:   "application/invalid",
			expectedStatus: fiber.StatusNotAcceptable,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			app := fiber.New()
			app.Use(NewAccepts("application/json"))
			app.Get("/", func(c *fiber.Ctx) error {
				return c.SendString("OK")
			})

			req := httptest.NewRequest(http.MethodGet, "/", nil)
			if tt.acceptHeader != "" {
				req.Header.Set("Accept", tt.acceptHeader)
			}

			resp, err := app.Test(req)
			assert.NoError(t, err)
			assert.Equal(t, tt.expectedStatus, resp.StatusCode)
		})
	}
}
