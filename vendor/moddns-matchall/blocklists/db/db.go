package db

import (
	"github.com/ivpn/dns/blocklists/db/repository"
	"github.com/ivpn/dns/libs/store"
)

// Db is an interface for database functionalities
type Db interface {
	store.Store
	repository.BlocklistRepository
}
