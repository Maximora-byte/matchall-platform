# MatchAll account DoT / DoQ

Deployed 2026-09-26. `compose.yaml` runs a read-only, bounded-resource Go gateway on TCP/UDP 853. Existing account tokens are reversibly encoded into a canonical 52-character base32 DNS label under `tls.dns.maximoraverse.org`; this hostname is a bearer credential, not public account metadata. Wildcard DNS A points to 64.110.101.75. No per-account certificates are issued.

Every query forwards over host loopback to the existing DoH account handler. No authorization, policy or response caching in transport layer; account disable, quotas, token rotation, modDNS fail-closed behavior, aggregation and optional query logging remain owned by the existing gateway. All forwarded transports share the loopback source IP limit (180 QPS / burst 360); per-account limits remain unchanged. DoT supports sequential queries on persistent connections; DoQ uses TLS1.3, ALPN doq, one framed message per bidirectional stream, ID0, no 0-RTT. Limits: 256 connections, 32/IP, 128 concurrent backend queries, 16 incoming QUIC streams/connection. These are configured resource ceilings, not measured production capacity.

Account page gives native Android Private DNS hostname (DoT), and quic://hostname:853 for compatible clients. Some clients use separate hostname/port fields. No original DoH address/token/profile/routing migration. SNI and bootstrap resolution may expose the account hostname to the network; do not claim total anonymity.

## Certificate and maintenance

Let's Encrypt wildcard cert under `/mnt/data/matchall-dns-transports/letsencrypt/live/matchall-dns-transports/`, expires 2026-12-25. Initial issuance was MANUAL DNS-01, NOT automatic renewal. Namecheap TXT `_acme-challenge.tls.dns` was manually supplied by the owner. Renew before expiry using a new DNS-01 challenge or configure a supported DNS automation/delegation method. Do not run unattended `certbot renew` expecting success until hooks exist. Gateway reloads certificate files on every handshake; no restart needed on successful renewal. Existing five-minute health report alerts at less than 30 days, on the operations page only; no external notification configured.

Certificate private material and transport source/binary are included in protected existing modDNS backup, not public artifacts. Host firewall only adds TCP/UDP853 before existing INPUT rejection; persistent additions are in `/etc/iptables/rules.v4`; originals in protected backups directory. Do not restore whole Docker runtime iptables snapshots blindly.

## Validation

- Four Go tests with race detection: canonical hostname, framing, per-query reauthorization/fail-closed responses, actual trusted DoT/QUIC handshakes with same-connection revocation.
- External Osaka server temporary-account probe: normal resolution, disabled refusal, rotated old-token refusal over both TCP and UDP853. Production account rows/tokens/mappings unchanged after cleanup.
- 84 existing Python tests pass. Existing public query-log/filter smoke passes with self-recursive modDNS upstream.
- Account HTML fetched using a temporary account, hostname matches actual token. Browser uses this sanitized live render plus public assets: clipboard and 1280/390/320 layouts pass; not a real Android/FlClash application test.
- No additional throughput benchmark this release.

## Recursive backend

`../dns-recursive` builds distro Unbound with DNSSEC validation, QNAME minimization, bounded caches, no query/reply logging, no forwarding configuration. Production is `recursive` service in `../moddns-production/compose.yaml`, fixed internal IP 172.25.0.53:5353. No public53 or host mapped port. modDNS alias `knot` now targets that private address because its plain DNS upstream parser rejects hostname addresses. Preserve subnet/IP on rebuild. Legacy account routing remains unchanged. Direct UDP/TCP tests: valid signed domain, bogus DNSSEC SERVFAIL, reserved invalid-domain NXDOMAIN. Full modDNS private DoH also validates signed/bogus results. Keep distro DNS root-data packages current (static root trust anchor file included in image).

Rollback: restore previous gateway compose image querylogs-production and app source bundle if necessary; set modDNS DNS_UPSTREAMS back to the protected original env value and recreate only proxy; stop new transports if withdrawing features. Never modify real accounts during rollback. Backups: `/mnt/data/matchall-dns-transports/backups/`; full snapshots `/mnt/data/matchall-moddns/backups/`.

## Public user guide

2026-09-26 published https://dns.maximoraverse.org/guide (no login needed). Source ../dns-platform/templates/guide.html, app GET route; shared title block and guide links in header/footer/account. Guide covers protocol selection, Android/Apple/browser/Windows, DoQ compatibility, manual-certificate operations caveat, filtering vs protocol choice, recursive DNSSEC, diagnostics, restoring original settings and token privacy. No personal credentials. Current gateway image matchall-dns:transports-guide. Backup previous app/compose/templates at protected backups/guide-20260926. Candidate local server and live public route browser tests pass1280/390/320, keyboard details, anchors, no overflow/console errors; linked privacy/contact200 and login302. Existing DNS code/policy untouched; public GET verified (FastAPI GET-only route does not enable HEAD). UI-only release, no additional protocol/throughput benchmark. Source is in existing untracked workspace, no commit claimed.

### Form Origin correction

2026-09-26: native browser POST forms were broken by document `no-referrer`, producing `Origin: null` rejected by exact-origin CSRF check. Changed DNS-only Caddy header, application response header and HTML referrer meta to `same-origin`; cross-origin links still do not send Referer. DO NOT fix by accepting `Origin: null` or disabling CSRF. Real browser cookies only (no forced Origin) reproduced403 and verified six formPOSTs303 after fix: query enable/clear/disable, filter prepare/enable, logout. Negative tests still reject null, hostile origins and incorrect token. 85tests pass; deployed image matchall-dns:csrf-origin-fix. Rollback bundle backups/csrf-origin-20260926 includes app/base/compose/Caddyfile. UI mock tests or clients manually supplying Origin cannot validate native navigation-form header behavior.
