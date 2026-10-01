package sendgrid

import (
	"context"
	"errors"
	"testing"

	"github.com/sendgrid/rest"
	sgmail "github.com/sendgrid/sendgrid-go/helpers/mail"
)

// mockSGClient implements the subset of sendgrid client we use
type mockSGClient struct {
	respCode int
	err      error
	last     *sgmail.SGMailV3
}

func (m *mockSGClient) Send(msg *sgmail.SGMailV3) (*rest.Response, error) {
	m.last = msg
	if m.err != nil {
		return nil, m.err
	}
	return &rest.Response{StatusCode: m.respCode}, nil
}

func TestVerify(t *testing.T) {
	m := New("https://srv", "k")
	if err := m.Verify("user@example.com"); err != nil {
		t.Fatalf("expected valid email, got %v", err)
	}
	if err := m.Verify(""); err == nil {
		t.Fatalf("expected error for empty email")
	}
	if err := m.Verify("bad-format"); err == nil {
		t.Fatalf("expected error for invalid format")
	}
}

func TestSendWelcomeAndReset(t *testing.T) {
	ctx := context.Background()
	c := &mockSGClient{respCode: 202}
	m := New("https://frontend", "k", WithClient(c))

	if err := m.SendWelcomeEmail(ctx, "user@example.com", "token123"); err != nil {
		t.Fatalf("welcome send failed: %v", err)
	}
	if err := m.SendPasswordResetEmail(ctx, "user@example.com", "prtkn"); err != nil {
		t.Fatalf("reset send failed: %v", err)
	}
}

func TestSendFailure(t *testing.T) {
	ctx := context.Background()
	m := New("https://frontend", "k", WithClient(&mockSGClient{respCode: 500}))
	if err := m.SendWelcomeEmail(ctx, "user@example.com", "tok"); !errors.Is(err, ErrFailedToSendEmail) {
		t.Fatalf("expected failed to send email, got %v", err)
	}
}

func TestSendBasicEmails(t *testing.T) {
	ctx := context.Background()
	c := &mockSGClient{respCode: 202}
	m := New("https://frontend", "k", WithClient(c))
	if err := m.SendWelcomeEmail(ctx, "user@example.com", "tok1"); err != nil {
		t.Fatalf("welcome basic send failed: %v", err)
	}
	if c.last == nil || c.last.TemplateID != "" {
		t.Fatalf("expected no template id for welcome, got %+v", c.last)
	}
	if err := m.SendPasswordResetEmail(ctx, "user@example.com", "tok2"); err != nil {
		t.Fatalf("reset basic send failed: %v", err)
	}
}
