package statistics

import (
	"context"

	"github.com/ivpn/dns/api/db/repository"
	"github.com/ivpn/dns/api/model"
)

type StatisticsService struct {
	StatisticsRepository repository.StatisticsRepository
}

func NewStatisticsService(db repository.StatisticsRepository) *StatisticsService {
	return &StatisticsService{
		StatisticsRepository: db,
	}
}

func (s *StatisticsService) GetProfileStatistics(ctx context.Context, profileId string, timespan string) ([]model.StatisticsAggregated, error) {
	timespanHours, err := model.NewTimespan(timespan)
	if err != nil {
		return nil, err
	}

	stats, err := s.StatisticsRepository.GetProfileStatistics(ctx, profileId, timespanHours)
	if err != nil {
		return nil, err
	}
	return stats, nil
}
