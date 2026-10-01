package auth

import "golang.org/x/crypto/bcrypt"

// CheckPasswordHash compares a password to a hash and returns if it is valid or not.
func CheckPasswordHash(password, hash string) bool {
	err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(password))
	return err == nil
}
