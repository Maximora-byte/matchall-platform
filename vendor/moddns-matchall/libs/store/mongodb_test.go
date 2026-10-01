package store

import "testing"

func TestBuildMongoCredentialsDefaultAuthSource(t *testing.T) {
	cfg := &Config{Username: "user", Password: "pass"}
	cred := buildMongoCredentials(cfg)
	if cred.AuthSource != "dns" {
		if cred.AuthSource == "" { // more explicit error
			// Should default to dns
			//nolint:goerr113 // simple test error
			t.Fatalf("expected default auth source 'dns', got empty string")
		}
		t.Fatalf("expected default auth source 'dns', got %q", cred.AuthSource)
	}
}

func TestBuildMongoCredentialsCustomAuthSource(t *testing.T) {
	cfg := &Config{Username: "user", Password: "pass", AuthSource: "admin"}
	cred := buildMongoCredentials(cfg)
	if cred.AuthSource != "admin" {
		t.Fatalf("expected auth source 'admin', got %q", cred.AuthSource)
	}
}
