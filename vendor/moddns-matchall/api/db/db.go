package db

import (
	"github.com/ivpn/dns/api/db/repository"
	"github.com/ivpn/dns/libs/store"
)

// Db is an interface for database functionalities
type Db interface {
	store.Store
	repository.AccountRepository
	repository.ProfileRepository
	repository.BlocklistRepository
	repository.QueryLogsRepository
	repository.SubscriptionRepository
	repository.StatisticsRepository
	repository.SessionRepository
	repository.WebAuthnCredentialRepository
}
