package model

import "testing"

func TestSetPassword(t *testing.T) {
	tests := []struct {
		name         string
		initialEmail string
		passwords    []string // sequence of passwords to set
		expectErrors []error  // expected errors per attempt
		validate     func(t *testing.T, acc *Account)
	}{
		{
			name:         "Empty password first",
			initialEmail: "user@example.com",
			passwords:    []string{""},
			expectErrors: []error{ErrEmptyPassword},
			validate: func(t *testing.T, acc *Account) {
				if acc.Password != nil {
					t.Fatalf("expected password pointer to remain nil for empty password")
				}
			},
		},
		{
			name:         "Single valid password",
			initialEmail: "user@example.com",
			passwords:    []string{"StrongPass123!@"},
			expectErrors: []error{nil},
			validate: func(t *testing.T, acc *Account) {
				if acc.Password == nil || len(*acc.Password) == 0 {
					t.Fatalf("expected hashed password to be set")
				}
			},
		},
		{
			name:         "Replace password",
			initialEmail: "user@example.com",
			passwords:    []string{"StrongPass123!@", "AnotherPass456!@"},
			expectErrors: []error{nil, nil},
			validate: func(t *testing.T, acc *Account) {
				if acc.Password == nil || len(*acc.Password) == 0 {
					t.Fatalf("expected hashed password to be set")
				}
			},
		},
		{
			name:         "Empty then valid password",
			initialEmail: "user@example.com",
			passwords:    []string{"", "StrongPass123!@"},
			expectErrors: []error{ErrEmptyPassword, nil},
			validate: func(t *testing.T, acc *Account) {
				if acc.Password == nil || len(*acc.Password) == 0 {
					t.Fatalf("expected hashed password after second set")
				}
			},
		},
	}

	for _, tt := range tests {
		acc := &Account{Email: tt.initialEmail}
		var previousHash string
		for i, pw := range tt.passwords {
			err := acc.SetPassword(pw)
			expectedErr := tt.expectErrors[i]
			if expectedErr != nil {
				if err != expectedErr {
					t.Fatalf("%s: expected error %v at attempt %d, got %v", tt.name, expectedErr, i, err)
				}
			} else if err != nil {
				t.Fatalf("%s: unexpected error at attempt %d: %v", tt.name, i, err)
			}

			// If this is not the first successful set, ensure hash changed
			if i > 0 && expectedErr == nil && previousHash != "" {
				if acc.Password != nil && *acc.Password == previousHash {
					t.Fatalf("%s: expected hash to change on attempt %d", tt.name, i)
				}
			}
			if err == nil && acc.Password != nil {
				previousHash = *acc.Password
			}
		}
		// Final state validations
		tt.validate(t, acc)
	}
}

// Auth method helpers removed; dynamic auth method computation is covered elsewhere.
