package store

// Config represents the database configuration
type Config struct {
	DbURI                 string
	Name                  string
	Username              string
	Password              string
	AuthSource            string
	MigrationsSource      string
	TLSEnabled            bool
	CertFile              string
	KeyFile               string
	CACertFile            string
	TLSInsecureSkipVerify bool // Only for testing & development, use false in production
}
