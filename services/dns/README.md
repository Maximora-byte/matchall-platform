# MatchAll DNS service portal

## IPv4 / IPv6 account setup (2026-09-27)

Account UI, guide, Windows instructions and Apple mobileconfig now support the production IPv4/IPv6 pair while retaining one token-bearing DoH/DoT/DoQ identity. Image `matchall-dns:dual-stack-20260927`; 88 tests, desktop/mobile browser checks and public temporary-account DoH/DoT/DoQ IPv6 acceptance passed. Existing account-state fingerprint remained unchanged. See `../network-dns-account-ipv6/README.md`.

## Brand asset update (2026-09-26 06:16 UTC)

Installed user-supplied MatchAll logo ZIP assets on DNS portal only: dark-background SVG header logo, SVG/ICO favicon and Apple touch icon. Added brand.css and updated shared base template; no authentication, token or resolver logic changed. Backup: `/srv/personal-blog/backups/dns-platform/20260926T061510Z` (SHA checks passed); rollback image `matchall-dns:before-logo-20260926`. Eight tests passed in isolated image. Public health/logo/favicon return success and browser confirms logo load with no horizontal overflow at 390px and 1280px. Other MatchAll sites and attachment's broader optimization suggestions were not changed.

## Account token update (2026-09-26 06:00 UTC)

User requested one shared token per account instead of per-device setup. Authenticated home now provisions/shows one account token automatically, with shared Apple profile and cross-platform instructions. A partial unique SQLite index guarantees one active token per subject. Legacy POST /devices is idempotent and cannot create additional tokens. POST /account/rotate atomically revokes the previous token and generates one replacement; all client configurations must then be updated. Limit is 60 QPS across the account's devices. Pre-change inspection: one user, zero active tokens, so no existing tokens revoked/migrated. Pre-change backup: `/srv/personal-blog/backups/dns-platform/20260926T055917Z`. Earlier per-device descriptions below are historical.

Public origin: https://dns.maximoraverse.org

## Deployment (2026-09-26)

- Source: `/root/.openclaw/workspace/main/dns-platform`
- Docker Compose project: `matchall-dns`; service: `dns-portal`; shared network: `personal-blog_blog_internal`.
- Runtime: `/srv/personal-blog/dns-platform`; SQLite under `data`; encrypted token key and OIDC secret under `secrets` (uid 10001, root-protected backups).
- Loopback application endpoint: `127.0.0.1:18084`; Caddy routes the public origin to `dns-portal:8000`.
- Authentik application/provider: MatchAll DNS, slug/client ID `matchall-dns`, strict callback `https://dns.maximoraverse.org/auth/callback`. Immutable user UUID subject; first login provisions account. No group restrictions or changes to existing enrollment.
- Authorization code + PKCE S256 + single-use state + nonce + RS256 ID token verification + userinfo subject match. Secure HttpOnly cookies and CSRF on mutations.
- Each user may create 20 active devices; random 256-bit tokens, SHA-256 lookup, Fernet-encrypted recovery for configuration downloads. Immediate revocation for subsequent requests. Tokens are bearer credentials, not hardware binding.
- GET/POST `/dns-query/{token}` validates credentials, DNS wire message and 60 QPS token bucket, then forwards encrypted to HK and falls back to backup on timeout/errors/SERVFAIL. No raw query history in portal database; only per-device aggregate counts. Existing AdGuard query logs remain on resolvers.
- A single gateway is NOT full geographic HA. All new clients' upstream traffic shares gateway source IP; existing per-source resolver limits remain unchanged. Existing standalone DoH/DoT public endpoints and configs are intentionally untouched.
- No application access logging; sensitive pages and profiles no-store, no-referrer. Do not enable raw URL logging (URLs carry bearer tokens).

## Verification completed

- Eight isolated automated tests: auth requirements, cross-account device/profile/revocation isolation, CSRF, signed OIDC callback and replay, profile parsing, token revocation, upstream failover/closed failure, malformed DNS, per-user device cap and token limiter.
- Live upstream smoke via temporary synthetic local account: example.com NOERROR, advertising NXDOMAIN, bad DNSSEC SERVFAIL; profile generation and revoked-token 404. Synthetic records removed.
- Real Authentik discovery and authorization redirect reach default authentication flow with no OAuth errors. This is NOT a completed real browser login.
- Both original `/dns-query` endpoints return HTTP 200 after deployment.
- Browser local preview was blocked by browser navigation policy. Do not bypass it; render/verify public origin after DNS is ready.

## Public handoff, 2026-09-26 05:53 UTC

User added A `dns -> 64.110.101.75`. Public DNS returns it; HTTPS home is 200. Let's Encrypt certificate expires 2026-12-25 04:50 UTC; Caddy manages renewal. Browser rendered homepage at desktop 1280px and mobile 390px without horizontal overflow. Screenshot capture stalled once; reopening the tab restored viewport/DOM checks (no pixel screenshot verdict claimed).

Public HTTPS synthetic-account smoke passed: device creation, profile, normal query, filtering, DNSSEC failure and immediate revocation. Test rows cleaned. Both original DNS public endpoints still HTTP 200. Authentik login button reaches real authentication flow with verification UI; no existing signed-in owner session. Owner must complete normal interactive login/verification for full real-account callback validation; no credentials requested or bypass applied. Eight isolated tests include signed callback validation and replay rejection, but do not replace that owner check.

Latest application backup at handoff: `/srv/personal-blog/backups/dns-platform/20260926T055313Z`.

## Backups / rollback

- Before IdP integration: `/srv/personal-blog/backups/authentik/authentik-20260926T053645Z`, both SHA-256 checks passed.
- Before Caddy change: `/srv/personal-blog/backups/dns-site-before-20260926T053715Z/Caddyfile`.
- App backups: `/srv/personal-blog/backups/dns-platform/`; `matchall-dns-backup.timer` daily, SQLite online backup + integrity check + code/secrets/Caddy archive and hashes. Backups contain token encryption key; protect them.
- Disable only new Caddy site and `docker compose -p matchall-dns -f compose.yaml stop`. Existing DNS resolver addresses do not depend on portal. Do not restore entire Authentik DB just to remove this new application; inspect scoped app/provider removal if needed.
- Restore DB and encryption key together. Do not run `provision.py` or `configure_authentik.py` again without inspection; these assert creation-only.

## Offline recovery verification

See [the recovery rehearsal runbook](../../docs/dns-recovery-rehearsal.md) for the
synthetic-tested SQLite restore verifier and current migration-5 backup sensitivity.
This is tooling, not evidence of a production restore. The portal remains limited to
one worker/replica; do not infer high availability from a passing offline rehearsal.
