package model

import "errors"

const (
	LAST_1_HOUR   = "LAST_1_HOUR"
	LAST_12_HOURS = "LAST_12_HOURS"
	LAST_1_DAY    = "LAST_1_DAY"
	LAST_7_DAYS   = "LAST_7_DAYS"
	LAST_MONTH    = "LAST_MONTH"
)

// NewTimespan returns the number of hours for the given timespan
func NewTimespan(timespan string) (int, error) {
	switch timespan {
	case LAST_1_HOUR:
		return 1, nil
	case LAST_12_HOURS:
		return 12, nil
	case LAST_1_DAY:
		return 24, nil
	case LAST_7_DAYS:
		return 24 * 7, nil
	case LAST_MONTH:
		return 24 * 30, nil
	}
	return 0, errors.New("invalid timespan")
}
