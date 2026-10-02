# MatchAll DNS management rollout — 2026-09-26

## Phase 1

Single Uvicorn worker explicitly pinned in Dockerfile. Account settings live in a separate keyed table, so legacy identity/token rows are untouched. Migration 1 is transactional and repeatable. OIDC issuer remains pinned; `sub` remains the unique identity. Existing login UPSERT updates only name, never enabled/QPS/role.

Admin bindings are host-managed only (`python admin_role.py SUBJECT [--revoke]`). The existing immutable subject was verified against Authentik's superuser flag before the initial binding. Changing Authentik group membership alone does **not** revoke this local binding: use this command. API role checks run on every request and again inside the update transaction. Cookie mutations require CSRF. Quota/status changes and successful audit record commit atomically. Authenticated rejected management attempts are recorded at most once per actor per minute (without raw URLs); anonymous denials are not stored.

Account status, token revocation and quotas are read on each DoH request, before any upstream or response cache. Changes affect the next authorization decision; already admitted requests may finish (12-second query deadline). No shared HTTP caching is allowed. Standalone resolver addresses remain outside this account gateway.

Account buckets key immutable sub, share devices/rotations, and are process-local. Default 60 QPS / 60 burst. Downward changes clamp balance without refilling. Increases do not fill balance. Process restart starts at configured burst; retained buckets are not evicted while running. Multiple workers/replicas remain prohibited until shared atomic limits and cross-process revocation are implemented.

## Statistics

All counters concern **recognized, currently non-revoked account tokens that reached the DoH handler**. Invalid tokens and earlier IP-level middleware rejections are excluded (no identifiable account). `received` includes disabled, limited and malformed requests; `admitted` means passed status and account bucket, before DNS format validation; `forwarded` means one validated logical query entering the upstream attempt stage; `success` means a validated matching non-SERVFAIL response (including NXDOMAIN and filtering); `failed` means no acceptable upstream response. `limited`, `disabled`, `invalid` are distinct counters. Retries never increment the logical-query counters again.

Minute buckets are batched, normally every 5 seconds. Sequential health probes can extend flush interval by up to about 10 seconds. If persistence fails or last successful flush is over 20 seconds old, new DoH requests fail HTTP 503 before adding statistics. A process crash can lose the current pending batch, covering up to 20 seconds of arrivals plus up to 12 seconds of in-flight completions (32-second arrival/completion horizon under a responsive event loop). A stalled process/OS cannot promise a wall-clock persistence bound. On disk failure, pending data remains in memory for retry but there is no guaranteed durability until SQLite recovers. Graceful shutdown flushes. Legacy device counters are displayed separately, not rewritten into the new window history. Retention: usage 30 days, audit 90 days, fallback events 7 days. Fallback events coalesce per endpoint/minute.

DNS health checks query example.com approximately every 30 seconds and report time, latency, rcode and sanitized errors. `/healthz` is only application/database liveness. No full gateway HA is claimed.

## Backups and rollback

Pre-change consistent backup: `/srv/personal-blog/backups/dns-platform/20260926T063240Z`. Protected archive includes encryption keys; do not publish it. Rollback image: `matchall-dns:before-admin-20260926`.

The real DB copy passed idempotent migration, unchanged users/devices/sessions, SQLite backup/restore and integrity checks. Stop only `dns-portal` for any data restore, preserve current DB/WAL/SHM in a protected recovery directory, restore the consistent DB and matching secrets together, then start one worker. Never replace the current database with the old snapshot merely for code rollback: doing so could resurrect revoked credentials. The old image can read the unchanged legacy tables, but it would no longer enforce new disabled/quota controls, so only use it after evaluating those controls and limiting access appropriately.

14 isolated tests passed. Public HTTPS synthetic-account smoke passed GET/POST, UI render, admin mutation/audit, disable/restore, quota display, token rotation and usage. Synthetic data removed. A real owner-driven login and authenticated browser interaction have not yet been exercised in this rollout.

## Final artifact and pilot boundary

Final 17-test image also contains a disabled-by-default modDNS adapter and migration 2. Production has no modDNS environment or mappings; all real users keep the original upstreams. The six-service isolated pilot and its real-DNS tests are described in `../moddns-lab/README.md`; it is not a production backend. Internal proxy marker counts produce `blocked` without domain logs. The current private/public pages retain no-store and noindex headers. Protected pre-final snapshot: `/srv/personal-blog/backups/dns-platform/20260926T065531Z`.

## Phase 2 opt-in release — 2026-09-26, supersedes pilot boundary above

Production image is now `matchall-dns:phase2-production`, configured against the durable private backend in `../moddns-production/compose.yaml`. User-initiated `/filters/enable` is live; ordinary login still does not migrate anyone. No real mapping existed at rollout completion. Default opt-in list is OISD Small; old URLs/tokens remain valid. Personalized traffic never falls back to legacy resolvers. Missing subscribed lists also fail closed (fork patch in proxy cache). A reconciliation stays pending through cache expiry before reopening traffic.

19 regression tests passed, plus focused Go failure tests. Public HTTPS synthetic test covered original parsing, CSRF, repeated opt-in, unchanged token, filter UI, GET/POST blocking and private marker suppression. Temporary account data was removed and real users/devices matched the pretest snapshot. Owner-interactive OIDC login remains untested. Capacity evidence: independent generator, 60 QPS for 120 seconds, 7,200/7,200 valid results, P95 14.39 ms, P99 22.27 ms on the internal gateway leg. At 120 QPS, 106/7,200 were correctly quota-rejected and latency increased; do not treat 120 as a guaranteed capacity.

Redis/proxy outages and subscribed-list loss returned failure without bypass and recovered correctly. Mongo/Redis/API container recreation retained policy. Internal certificate forced rotation preserved TLS validation and filtering. Root-only backup verification includes SQLite integrity and complete checksums; fixed a former checksum manifest bug involving temporary WAL/SHM files. Use the new latest snapshot, not the earlier incomplete manifests. Daily backup (14-day retention), certificate renewal and 5-minute host-health timers are installed. Same-disk backup is not off-host disaster recovery. See `../moddns-production/README.md` for deletion, restore, monitoring and rollback boundaries; laboratory, restoration and stage containers are stopped.

## Phase 3 operations release — 2026-09-26

`matchall-dns:phase3-production` adds `/admin/operations` and `/api/admin/operations`, plus filtering state/routing/management revision and explicit recovery actions in `/admin`. No query domains, tokens or credentials are exposed by the operations endpoints. No database migration or automatic user routing is performed. Admin pages use the existing no-store/noindex behavior.

Recovery accepts existing non-deleted mappings only, does not change account enablement or routing, verifies immutable account/profile ownership, waits through the proxy cache TTL, and commits ready state with completion audit atomically. Admin privilege is rechecked before starting and before final commit; revocation or audit failure leaves routing closed. Ready mappings are an idempotent no-op. Active account operations share a process-local lock. Orphaned pending/updating states must be older than 60 seconds before recovery. Tombstones cannot be overwritten by an overlapping recovery/update. This is still a single-worker protocol, not distributed coordination. Recovery reads the current remote saved policy; it does not roll back an ambiguous previous rule write.

The host health job verifies all three latest snapshot checksums, backup age, free-space reserve, container state/OOM and leaf-certificate expiry. It publishes only a sanitized report to `public-status/health.json`, atomically replaced, mounted read-only at `/run/dns-health`. The web process gets no Docker socket or backup-directory access. A missing or older-than-15-minute report is shown as unhealthy, never green; DNS probe data older than 90 seconds is also marked stale. Alerts are visible in the admin UI/systemd, not sent externally.

31 isolated tests passed, including role/CSRF denial, disabled-account preservation, route/revision preservation, tombstone guards, in-flight conflicts, role revocation mid-recovery, identity mismatch, audit failure and report staleness. Public HTTPS synthetic admin/target acceptance passed error-state refusal, recovery, disabled-state preservation, unchanged profile/revision, repeated recovery, actual blocking and audit count. All pre-existing users/devices/settings/mappings matched before/after; synthetic fixtures removed. Real-owner interactive login remains unexercised.

Pre-change bundle: `/mnt/data/matchall-moddns/backups/phase3-before-20260926T073707Z`. Code rollback: select `matchall-dns:phase2-production` in the gateway compose and recreate only the gateway; keep the current DB, endpoint/key/CA settings and persistent backend. No database restore is needed. This phase does not add gateway HA, second proxies, external alert delivery or off-host backups.

## Aggregate statistics dashboard — 2026-09-26

Image `matchall-dns:statistics-production`. User view `/statistics`, administrator site-wide view `/admin/statistics`; JSON equivalents `/api/statistics` and `/api/admin/statistics`. `period` accepts only `24h`, `7d`, `30d`. User subject always comes from the authenticated session; a query parameter cannot change scope. All routes remain no-store/noindex. No raw domains, query logs, tokens, third-party chart services or CDN dependencies were added.

Ranges are minute-granular rolling intervals ending with the current incomplete minute; 24 hourly buckets, 7 or 30 24-hour buckets, labelled UTC. Missing intervals render zero recorded counts, not an availability assertion. Null rate intervals are not connected by a chart line. Summary rates are weighted from total counts, never averages of bucket percentages. Requests and completions can land in different minute buckets. Existing aggregate retention stays 30 days. Empty histories are not fabricated.

Schema migration 3 adds `usage_subject_window(sub,window)` and its activation timestamp; existing users/devices/mappings are untouched. The proxy's trusted marker now atomically adds `filter_success` plus `filter_blocked` (when blocked), preserving the previous `blocked` counter. Filtering rate is **filter_blocked/filter_success**, excluding legacy successes and old blocked-only history. No eligible samples means null/“暂无数据”, not 0%. The activation time is shown in the UI. Existing historical `blocked` counts remain available separately. Legacy resolvers cannot supply trustworthy block counts.

Charts are server-rendered accessible SVG plus self-hosted JavaScript series toggles, with an expandable numeric table. Narrow screens use contained horizontal chart/table scrolling, not page overflow. Fixed the old mobile selector that hid the first link of every nav and removed an empty data-URL CSS import that violated existing CSP; CSP was not loosened.

40 isolated tests passed. Chromium at 1440px and 390px verified populated count/rate charts, curve hide/restore, 24h/7d/30d controls, table row counts, admin view, no page overflow and no console errors. Browser charts used synthetic data in isolated temporary containers only. `moddns-production/statistics_smoke.py` uses actual public HTTPS DNS requests from a temporary account to verify 1 legacy success + 2 modDNS successes (1 blocked) => 50% filtering rate, permissions, all periods and unchanged real user state. Real-owner interactive OIDC login remains outside these tests.

Rollback source/config bundle: `/mnt/data/matchall-moddns/backups/statistics-before-20260926T080645Z`. Previous image `matchall-dns:phase3-production` remains available. Roll back code only, retaining current DB, backend endpoints/keys and policy mapping; migration 3 and extra aggregate metrics are additive and compatible. No old token database restore is needed.


## Statistics tools — 2026-09-26

Image `matchall-dns:statistics-tools-production` adds optional 30-second refresh, manual refresh, aggregate CSV exports, and administrator account filtering. Auto-refresh defaults off, remembers the choice for the browser session, pauses in hidden tabs, and defers while chart content has focus or text selection. Updates preserve hidden curves, expanded tables and contained scroll positions. Network errors preserve previous data with an explicit message; 401/403 clears the statistics and disables auto-refresh.

`/statistics.csv` always exports the session owner's aggregates. `/admin/statistics`, `/api/admin/statistics`, `/admin/statistics.csv` accept optional `account` immutable subject; an unknown account is 404, never a fallback to global totals. The latest 200 accounts appear in the selector and each account on `/admin` links to its scoped view. Range links, refreshes and exports preserve scope. CSV uses UTF-8 BOM, UTC ISO timestamps and numeric values only, includes 24/7/30 bounded rows, leaves missing filtering rates empty, and excludes names, subjects, domains and credentials. Permissions are checked per request; all exports remain no-store.

42 tests passed. Isolated Chromium verified scope retention, actual CSV download, manual/automatic refresh, state retention, background/disabled refresh pause, 390px layout and clean console. Public `../moddns-production/statistics_tools_smoke.py` verified actual query counts 1 vs 2, all export ranges, own/admin isolation, missing accounts and role revocation. Synthetic accounts were cleaned up, real identities/tokens/settings/mappings unchanged. No schema migration, query logging or filtering migration was added.

Protected pre-change source/config bundle: `/mnt/data/matchall-moddns/backups/statistics-tools-before-20260926T081901Z`. Code-only rollback image: `matchall-dns:statistics-production`; recreate only the gateway, keeping current DB and backend configuration. Real-owner interactive OIDC login remains untested.


## Advanced filtering, first batch — 2026-09-26

Gateway image `matchall-dns:advanced-production`; private API binary updated (manifest in ../moddns-production/binary-sha256.json). Added private-only service catalog/on/off, bulk rules, rule metadata/group operations, and a narrow rebinding boolean endpoint. Arbitrary profile patch, logs and native auth routes remain unavailable. Profile ownership remains enforced upstream and in the gateway; user requests cannot select an arbitrary profile. No proxy binary/settings or real-account policy was changed by deployment.

`/filters/prepare` creates a dormant profile without routing; imported/dormant users can enter `/filters` from their account page before opt-in. Advanced writes keep routing unchanged, use the same per-account lock, updating/error state, cache-expiry wait and audit as existing policy writes. Disabled accounts cannot mutate. New HaGeZi Multi Light and AdGuard DNS Filter lists are downloaded alongside OISD Small; existing subscriptions are unchanged. No automatic opt-in or service/rebinding switch.

`/filters/advanced` supports append-only imports (up to200 rules/request; remote chunks20), per-rule group/note, group create/note/rename/remove, service on/off and rebinding. Group removal retains member rules. Groups/notes are organizational, not filtering precedence. The upstream default canonicalizes domains to wildcard form (includes subdomains); import mirrors this before matching metadata and duplicate detection. Duplicate normalized values are skipped even if their requested action differs; existing actions/metadata are preserved. Partial remote failure stays error, explicitly reports possible partial persistence and needs admin reconciliation; no false atomicity claim. A retried import won't overwrite already-created rule metadata: inspect/edit metadata after recovery if necessary.

`/filters/rules.json` exports only action/value/group/note in `matchall-rules-v1`, no account/profile IDs or tokens. Import accepts this JSON or newline rules; domain, wildcard-domain, IP and ASN supported, not arbitrary Adblock syntax. Exports may exceed200 rules, in which case split rules into batches for import. Empty group registry and group notes are not included: this is rule export, not complete profile backup. Logs remain disabled. Service presets combine domain and ASN scopes and can affect other products/CDNs; UI explains this. Rebinding may affect public names resolving to LAN addresses and can be overridden by custom allow rules.

56 isolated gateway tests and Go api/profile suites passed. Private cross-account mutations denied. Isolated actual DNS tests verified custom filtering, service/rebinding on/off and new lists on/off; browser1440/390 verified import, notes, download, no overflow and clean console. See ../moddns-production/advanced-acceptance. Isolated browser uses a synthetic cookie, not owner OIDC login.

Pre-change protected bundle: `/mnt/data/matchall-moddns/backups/advanced-before-20260926T091445Z`. Gateway code rollback to `statistics-tools-production` retains current DB/backend. The old gateway remains compatible with new API. Do not remove a newly subscribed list or restore an old API/proxy blindly after users create advanced policies; retain their persisted settings and current compatible engine. No full database rollback is required.


## Filtering configuration backup and restore — 2026-09-26

Image `matchall-dns:config-production`, gateway-only deployment, no DB migration or private backend changes. `/filters/config` provides JSON file selection/paste, read-only diff preview and explicit replace confirmation. `/filters/config.json` exports the currently exposed filtering scope: rule values/actions/group/notes, registry including empty groups and group notes, blocklist subscriptions, services and rebinding. `matchall-filter-config-v1` is a MatchAll format, NOT an upstream modDNS export or full account backup. No account/profile IDs, credentials, routes, logs, DNSSEC/upstream settings or display-order state. Base matching semantics are compatibility guards and must match current settings, not writable controls. More than1000 rules /100 groups per action /800KB is rejected, never silently truncated. Group registry names obey upstream64-byte limit.

Preview is stateless: an encrypted authenticated envelope using a purpose-derived key from the token-encryption key, bound to exact session hash, subject, mapping identity, revision, routing and canonical before-state fingerprint, with600s TTL. Token never becomes a public DNS credential. Applying requires current auth, CSRF, enabled account and explicit confirmation; acquires shared per-account lock; rechecks ready state, all binding fields, current content and live catalogs. Unknown/unavailable lists/services, unknown JSON keys, duplicate keys/rule values, conflicting normalized rules and incompatible semantics rejected before writes. No-op is read-only. Applied/failed changed previews cannot replay because revision/state changes.

Restore updates/removes/adds only specified filtering scope, verifying the exact canonical snapshot afterward, then waiting1.1s for cache expiry before marking ready and incrementing revision with audit. Multi-call restore is NOT atomic across Mongo/Redis: uncertain failures remain error, personalized routing fails closed, operator reconciliation required. Original routing and account enabled state are never modified by restoration. Download original configuration before apply to provide a user-held rollback; server preview tokens expire and are not a durable configuration-history service.

70 tests passed for validation, no-write preview, exact restore, content/revision/routing staleness, owner/session binding, tamper/expiry/replay denial, disabled/CSRF guards, partial failure and no-op. Isolated actual DNS validated restored rule/service/rebinding effects then rollback. Browser desktop/mobile validated file selection, previews, consent/apply, JSON download and restoring original, no console errors/overflow. Fixed upstream group metadata read adapter: group `comment` vs rule `note`; existing group comments were stored but not displayed by previous template.

Evidence: ../moddns-production/config-acceptance, config_acceptance.py, config_public_smoke.py. Protected pre-change bundle `/mnt/data/matchall-moddns/backups/config-restore-before-20260926T094610Z`. Code-only rollback image `matchall-dns:advanced-production`; retain current DB and backend policies. Real-owner interactive OIDC login not exercised; synthetic sessions used for tests.

## Opt-in query history — 2026-09-26

**Historical release record, superseded by migration 5.** The RAM-only statements
below describe the migration-4 release, not the current implementation. See the
current persistence and backup boundary immediately after this record.

`/queries` and `/api/queries` are session-owner-only (including administrators). Default OFF; explicit consent enables subsequent admitted, valid requests. SQLite migration 4 persists only enabled/retention preferences. Query rows remain bounded in one-worker RAM: 2,000 per account, 20,000 globally, oldest evicted; 1h/24h TTL with 30s pruning, also pruned on access. Restart clears all rows but preserves consent preference. No client IP, token or full answer stored. These controls do not change legacy upstream logging. Rankings reflect retained samples only.

Clear/disable increments an epoch to reject pre-clear in-flight writes. Disable clears synchronously. Quick rule actions show a normal CSRF-protected prefilled form; preview never writes policy or changes routing. Trusted proxy markers alone classify blocking; NXDOMAIN and upstream failure remain distinct. Before-validation rejections are excluded. Aggregate counters remain independent. Content is never in SQLite/Mongo/Redis or backups. Do not add Uvicorn workers without redesigning this RAM store and the existing limiter. Roll back gateway image to `matchall-dns:config-production`; migration 4 can remain.

84 tests passed. Isolated real responses/blocking/failure verified; the chosen .invalid probe returned SERVFAIL, not NXDOMAIN (NXDOMAIN classification separately covered in tests). With logging enabled, 60 QPS for 45 seconds yielded 2,700/2,700 valid responses, P95 15ms, P99 179ms; cap remained 2,000. This is tested load, not maximum capacity.

Desktop/mobile browser and public synthetic opt-in/clear/disable/rankings passed. Real account fingerprints and remote policies unchanged, real log-enabled0/routed0. Stage restart removed tmpfs SQL too, so persistence was verified in lifecycle tests, not that live-stage restart.
## Current query history and backup boundary — migration 5

The current `query_history.py` persists opted-in query rows in the SQLite
`query_history` table. History remains OFF by default and requires explicit consent.
It survives process restarts; the historical RAM limits and restart-clears-history
claim above apply only to migration 4. No client IP, credential or full DNS answer
is stored by this feature.

Retention values are `3600` (one hour), `86400` (24 hours) and `0` (no automatic
expiry). Cleanup operates on current rows; `0` does not imply a bounded history or
automatic database-size cap. Consent preferences and clear/disable coordination
still rely on process-local state. Keep one Uvicorn worker and one replica.

Clear deletes the owner's current rows. Disable also clears them and rejects
pre-disable in-flight records. Neither operation erases already-created database
backups. A SQLite online-backup snapshot can include opted-in domains, timestamps
and outcomes, along with identity/session/token material. Treat these bundles as
private data: apply the approved access, encryption, off-host handling, expiration
and deletion policy to backup copies too. No production policy or user retention
setting is changed by this documentation correction.

See [the current recovery and sensitive-data boundary](../../docs/dns-recovery-rehearsal.md#current-sensitive-data-not-historical-assumptions).
A passing offline verifier does not prove backup-key pairing, remote-backend
restoration or production recoverability.
