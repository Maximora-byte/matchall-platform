module github.com/ivpn/dns/blocklists

go 1.26.8

require (
	github.com/alicebob/miniredis/v2 v2.39.0
	github.com/getsentry/sentry-go v0.49.0
	github.com/getsentry/sentry-go/zerolog v0.49.0
	github.com/go-co-op/gocron/v2 v2.22.0
	github.com/google/uuid v1.6.0
	github.com/ivpn/dns/libs v0.0.0
	github.com/prometheus/client_golang v1.24.1
	github.com/redis/go-redis/v9 v9.22.0
	go.mongodb.org/mongo-driver v1.17.10
)

replace github.com/ivpn/dns/libs => ../libs

require (
	github.com/beorn7/perks v1.0.1 // indirect
	github.com/buger/jsonparser v1.1.2 // indirect
	github.com/cenkalti/backoff/v4 v4.3.0 // indirect
	github.com/golang-migrate/migrate/v4 v4.20.1 // indirect
	github.com/golang/snappy v1.0.0 // indirect
	github.com/jonboulle/clockwork v0.5.0 // indirect
	github.com/klauspost/compress v1.19.1 // indirect
	github.com/kylelemons/godebug v1.1.0 // indirect
	github.com/mattn/go-colorable v0.1.14 // indirect
	github.com/mattn/go-isatty v0.0.22 // indirect
	github.com/montanaflynn/stats v0.7.1 // indirect
	github.com/munnerz/goautoneg v0.0.0-20191010083416-a7dc8b61c822 // indirect
	github.com/prometheus/client_model v0.6.3 // indirect
	github.com/prometheus/common v0.70.1 // indirect
	github.com/prometheus/procfs v0.21.1 // indirect
	github.com/xdg-go/pbkdf2 v1.0.0 // indirect
	github.com/xdg-go/scram v1.1.2 // indirect
	github.com/xdg-go/stringprep v1.0.4 // indirect
	github.com/youmark/pkcs8 v0.0.0-20240726163527-a2c0da244d78 // indirect
	github.com/yuin/gopher-lua v1.1.1 // indirect
	go.uber.org/atomic v1.11.0 // indirect
	go.yaml.in/yaml/v3 v3.0.5 // indirect
	golang.org/x/crypto v0.57.0 // indirect
	golang.org/x/sync v0.23.0 // indirect
	golang.org/x/sys v0.48.0 // indirect
	golang.org/x/text v0.42.0 // indirect
	google.golang.org/protobuf v1.36.12 // indirect
)

require (
	github.com/cespare/xxhash/v2 v2.3.0 // indirect
	github.com/robfig/cron/v3 v3.0.1
	github.com/rs/zerolog v1.35.1
	github.com/spf13/cast v1.10.0
	github.com/stretchr/testify v1.12.1
)
