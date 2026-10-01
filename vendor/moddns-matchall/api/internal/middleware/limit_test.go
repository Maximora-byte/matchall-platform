package middleware

import (
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/ivpn/dns/api/config"
)

func TestNewLimitDisabled(t *testing.T) {
	cfg := &config.APIConfig{DisableRateLimit: true}
	InitLimitConfig(cfg)
	app := fiber.New()
	app.Use(NewLimit(1, time.Minute))
	count := 0
	app.Get("/test", func(c *fiber.Ctx) error {
		count++
		return c.SendStatus(200)
	})
	// Perform multiple requests which would normally exceed limit
	for i := 0; i < 5; i++ {
		req := httptest.NewRequest("GET", "/test", nil)
		resp, err := app.Test(req, -1)
		if err != nil {
			t.Fatalf("request failed: %v", err)
		}
		if resp.StatusCode != 200 {
			t.Fatalf("expected 200, got %d", resp.StatusCode)
		}
	}
	if count != 5 {
		// Ensure all requests passed through
		// (No rate limiting blocked them)
		// This is a sanity check to ensure our no-op handler ran.
		// In case of real limiter, some requests would not hit the endpoint.
		// Fiber limiter returns 429 before executing route handler.
		// So count would be less in that case.
		// Here we expect full passthrough.
		t.Fatalf("expected handler executed 5 times, got %d", count)
	}
}

func TestNewLimitEnabled(t *testing.T) {
	cfg := &config.APIConfig{DisableRateLimit: false}
	InitLimitConfig(cfg)
	app := fiber.New()
	app.Use(NewLimit(2, time.Minute))
	app.Get("/test", func(c *fiber.Ctx) error {
		return c.SendStatus(200)
	})
	// First two should succeed
	for i := 0; i < 2; i++ {
		req := httptest.NewRequest("GET", "/test", nil)
		resp, err := app.Test(req, -1)
		if err != nil {
			t.Fatalf("request failed: %v", err)
		}
		if resp.StatusCode != 200 {
			t.Fatalf("expected 200, got %d", resp.StatusCode)
		}
	}
	// Third should be limited
	req := httptest.NewRequest("GET", "/test", nil)
	resp, err := app.Test(req, -1)
	if err != nil {
		// Some environments might wrap errors differently
		// We still want to see a response.
		t.Fatalf("third request failed: %v", err)
	}
	if resp.StatusCode != 429 {
		// Expect 429 Too Many Requests
		t.Fatalf("expected 429 on third request, got %d", resp.StatusCode)
	}
}
