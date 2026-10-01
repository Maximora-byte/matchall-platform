package model

type StatisticsAggregated struct {
	Total int `json:"total"` // Note: "total" needs to be the same as in the repository mongo query
}
