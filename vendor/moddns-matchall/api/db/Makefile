BINARY_NAMES="golang-migrate|migrate"
DATABASE="mongodb://admin:admin@localhost:27017/dns"
MIGRATIONS_PATH=file://mongodb/migrations

.PHONY: help
help: ## Displays the help for each command.
	@grep -E '^[a-zA-Z_-]+:.*## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

up: ## Migrates the database to the latest version.
	migrate -database="$(DATABASE)" -source $(MIGRATIONS_PATH) -lock-timeout=20  -verbose up

down: ## Migrates the database down by first version.
	migrate -database="$(DATABASE)" -source $(MIGRATIONS_PATH) -lock-timeout=20 -verbose down

drop: ## Drops the database.
	migrate -database="$(DATABASE)" -source $(MIGRATIONS_PATH) -lock-timeout=20 -verbose drop -f

ver: ## Prints the current migration version.
	migrate -database=$(DATABASE) -source $(MIGRATIONS_PATH) -lock-timeout=20 version

force: ## Force the migrates the database to the given version. ex: version=1
	migrate -database="$(DATABASE)" -source $(MIGRATIONS_PATH) -lock-timeout=20 -verbose force $(version)

goto: ## Goto migrates the database to the given version. ex: version=1
	migrate -database="$(DATABASE)" -source $(MIGRATIONS_PATH) -lock-timeout=20 -verbose goto $(version)

reset: drop up ## Reset database to the latest version.
