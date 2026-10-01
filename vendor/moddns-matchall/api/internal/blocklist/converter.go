package blocklist

// BlocklistConverter is a converter for blocklist objects
// There are three most common syntaxes for blocklists: AdBlock, /etc/hosts, and domains only
// More info: https://adguard-dns.io/kb/general/dns-filtering-syntax/
// Currently, only domains syntax is supported
type BlocklistConverter struct{}
