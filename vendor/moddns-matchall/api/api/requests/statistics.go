package requests

type StatisticsQueryParams struct {
	Timespan string `json:"timespan" validate:"oneof=LAST_1_HOUR LAST_12_HOURS LAST_1_DAY LAST_7_DAYS LAST_MONTH"`
}
