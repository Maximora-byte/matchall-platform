package mongodb

import (
	"context"
	"time"

	"github.com/ivpn/dns/api/db/errors"
	"github.com/ivpn/dns/api/model"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
)

// StatisticsRepository is a MongoDB repository for statistics timeseries collections
type StatisticsRepository struct {
	DbName         string
	CollectionName string
	statsColl      *mongo.Collection
}

// NewStatisticsRepository creates a new StatisticsRepository instance
func NewStatisticsRepository(client *mongo.Client, dbName, collectionName string) StatisticsRepository {
	repo := StatisticsRepository{
		DbName:         dbName,
		CollectionName: collectionName,
	}
	repo.statsColl = client.Database(repo.DbName).Collection(collectionName)

	return repo
}

// GetProfileStatistics retrieves aggregated statistics for a profile
func (r *StatisticsRepository) GetProfileStatistics(ctx context.Context, profileId string, timespan int) ([]model.StatisticsAggregated, error) {
	matchFilter := bson.D{
		primitive.E{Key: "profile_id", Value: profileId},
	}

	if timespan != 0 {
		matchFilter = append(matchFilter, bson.E{
			Key: "timestamp",
			Value: bson.D{
				primitive.E{Key: "$lte", Value: time.Now()},
				primitive.E{Key: "$gte", Value: time.Now().Add(time.Duration(-timespan) * time.Hour)},
			},
		})
	}

	matchStage := bson.D{
		primitive.E{Key: "$match", Value: matchFilter},
	}

	groupFilter := bson.D{
		primitive.E{Key: "_id", Value: nil},
		// Note: "total" needs to be the same as in the model
		primitive.E{Key: "total", Value: bson.D{
			primitive.E{Key: "$sum", Value: "$queries.total"},
		}},
	}

	groupStage := bson.D{
		primitive.E{Key: "$group", Value: groupFilter},
	}

	pipeline := mongo.Pipeline{matchStage, groupStage}

	cursor, err := r.statsColl.Aggregate(ctx, pipeline)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return nil, errors.ErrAccountNotFound
		}
		return nil, err
	}

	results := make([]model.StatisticsAggregated, 0)
	if err = cursor.All(ctx, &results); err != nil {
		return nil, err
	}
	if len(results) == 0 {
		return []model.StatisticsAggregated{{Total: 0}}, nil
	}

	return results, nil
}
