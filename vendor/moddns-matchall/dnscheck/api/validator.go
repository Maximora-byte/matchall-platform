package api

import (
	"errors"
	"fmt"

	"github.com/go-playground/validator/v10"
	"github.com/gofiber/fiber/v2"
	"github.com/rs/zerolog/log"
)

type APIValidator struct {
	Validator *validator.Validate
}

func (v APIValidator) Validate(data interface{}) []ErrorResponse {
	validationErrors := []ErrorResponse{}

	errs := v.Validator.Struct(data)
	if errs != nil {
		for _, err := range errs.(validator.ValidationErrors) {
			var elem ErrorResponse

			elem.FailedField = err.Field() // Export struct field name
			elem.Tag = err.Tag()           // Export struct tag
			elem.Value = err.Value()       // Export field value
			elem.Error = true

			validationErrors = append(validationErrors, elem)
		}
	}

	return validationErrors
}

// ValidateRequest validates the request payload according to the provided struct tags
func (v APIValidator) ValidateRequest(c *fiber.Ctx, payload interface{}, errMsg string) []string {
	errMsgs := make([]string, 0)
	if errs := v.Validate(payload); len(errs) > 0 && errs[0].Error {

		for _, err := range errs {
			validationErr := fmt.Sprintf(
				"[%s]: '%v' | Needs to implement '%s'",
				err.FailedField,
				err.Value,
				err.Tag,
			)
			log.Error().Str("path", c.Route().Path).Err(errors.New("validation error")).Msg(validationErr)
			errMsgs = append(errMsgs, validationErr)
		}

		return errMsgs
	}
	return errMsgs
}
