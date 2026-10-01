package repository

import (
	"context"

	"github.com/ivpn/dns/api/model"
)

type StatisticsRepository interface {
	GetProfileStatistics(ctx context.Context, profileId string, timespan int) ([]model.StatisticsAggregated, error)
}
