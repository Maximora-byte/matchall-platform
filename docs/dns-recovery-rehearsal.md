# DNS recovery rehearsal before any redundancy work

## Status and hard boundary

This repository change supplies an **offline SQLite restore verifier**, synthetic
fixtures, and a runbook. It does not establish that a production backup can be
recovered. No real backup, key, server, account, deployment, or replica is used by the
automated tests. No live restore command, scheduler, remote access, or production
backup-job change is included.

Keep the DNS portal at **one Uvicorn worker and one replica**. A passing SQLite drill
is necessary recovery evidence, not permission or proof to scale the service.

## What the tool proves

From an explicitly supplied offline directory containing exactly the expected
manifest entries (`dns.sqlite3`, `config.tar.gz`, and `SHA256SUMS`),
`services/dns/restore_verify.py`:

1. Reads a strict SHA-256 manifest and makes checksum-verified protected copies in a
   newly created temporary directory. It rejects input symlinks and DB WAL/SHM/journal
   siblings: supply a consistent standalone SQLite online-backup snapshot, not files
   copied from a running data directory
2. Streams the config archive without extracting members. It rejects absolute or
   traversal paths, duplicate paths, links, devices, sparse files, special permission
   bits, excess entries/sizes, and unreadable/truncated member data
3. Opens the scratch database read-only/immutable with trusted schema disabled;
   checks SQLite integrity, foreign keys, required current schema/migrations 1–5,
   account-state ownership, and the one-active-token uniqueness constraint
4. Restores the scratch source to another fresh SQLite database using SQLite's backup
   API, repeats checks, and compares complete schema/table contents with an in-memory
   logical digest. This includes revoked credentials, disabled accounts, routing,
   revisions, mappings, sessions, query-history preferences and query-history rows
5. Removes scratch copies on normal completion and returns a small JSON result. It
   never prints archive member names, rows, domain history, tokens, or fingerprint
   values. It has no option to overwrite a selected destination, does not import the
   application, and neither starts services nor contacts network endpoints

Bounds: database 512 MiB, compressed archive 128 MiB, expanded archive 512 MiB, 10,000
archive members, 30-second SQLite query budget per database. Larger/newer bundles
require a reviewed tool adjustment; do not silently truncate or skip them. Temporary
storage needs room for two databases plus the compressed archive. Cleanup is ordinary
file removal, **not secure erasure**; use an encrypted disposable scratch volume.
An OS kill/power loss can leave scratch files, which the operator must handle as
sensitive data. SHA-256 detects corruption against the supplied manifest; it does not
prove source authenticity, freshness, or an untampered manifest.

The archive is not extracted, and matching encryption keys are not validated. Mongo,
Redis, modDNS policy/certificate state, external identity, proxy caches, and the live
service are outside this verifier. The report explicitly lists these limits; a
`verified: true` result applies only to its stated offline scope.

## Operator-approved rehearsal

Do not run this against production data from a development checkout or CI. Use an
owner-approved offline copy on an isolated, access-controlled disposable recovery
host with sufficient encrypted scratch storage and blocked outbound service access.
Real-data access, transfer, and restoration need separate authorization.

1. Record the backup identifier/time and approved RPO/RTO target in the private
   operational record. Verify trusted manifest provenance and off-host-copy freshness.
   Check that database, config/keys, and backend snapshots belong to the same recovery
   point. Never paste these bundles, keys, raw manifests, or dumps into a PR
2. As an unprivileged recovery operator, run:
   `python services/dns/restore_verify.py --bundle /approved/offline/dns-bundle`
   Exit 0 means this narrow drill passed. Exit 1 is a failed/unreadable bundle; do not
   continue. Missing arguments exit 2. Retain only the sanitized result with the
   approved backup identifier; the tool intentionally does not choose a latest backup
3. For a complete rehearsal, separately restore the corresponding config/secrets and
   modDNS persistent backend into approved isolated volumes. Verify database/key
   pairing using designated synthetic credentials, not a real account or live token.
   Confirm encrypted configuration can be recovered and private policies match the
   intended recovery point. These steps are manual gates, not tool capabilities
4. Start exactly one isolated portal worker only after reviewing configuration and
   egress isolation. Prevent OIDC, SMTP, DNS forwarding, timers, backend writes, and
   notifications from reaching production. Use local fixture/mock endpoints. Verify
   login/session boundaries, revoked-token denial, disabled-account denial, configured
   quota, unchanged routes/revisions/ownership, pending/error fail-closed behavior,
   and opted-in history consent/retention. Live owner-driven acceptance, if later
   desired, requires its own approved plan
5. Record actual elapsed recovery time and recoverable snapshot time, outcomes,
   residual gaps, and sign-off. Remove isolated volumes securely under the host's
   data-handling policy. A synthetic CI result must never be recorded as a production
   restore or an off-host disaster-recovery rehearsal

## Explicit backup generation

`services/dns/backup.py` is an explicit CLI: importing it performs no backup,
database access, directory creation, or umask change. All source/destination
arguments are required; running it without arguments fails before touching files.
An operator-reviewed invocation uses existing, approved inputs, for example:

```sh
python services/dns/backup.py \
  --database /approved/runtime/dns.sqlite3 \
  --config /approved/config/dns \
  --config /approved/config/Caddyfile \
  --output /approved/private/backup-directory
```

These are placeholders, not a deployment or test command. Existing scheduled
jobs that invoked the old no-argument script must be reviewed and updated before
adopting this version. This repository does not install or change those jobs.

The producer opens the existing source read-only and uses SQLite online backup
(including committed WAL data). It creates a private `.pending-*` staging directory,
archives only regular files/directories, writes the two-file SHA256SUMS contract,
then runs the existing offline verifier. Only a complete, verified bundle is renamed
to its final sibling directory. Ordinary failures clean staging; process termination
may leave an orphan `.pending-*`, which consumers must ignore. Do not select backups
solely by directory modification time: require the exact manifest and verify it.
Explicit bundle names never overwrite an existing destination.

Bundles are mode 0700 and files 0600. The offline verifier's size/schema limits
apply to generation too. No encryption, off-host transfer, scheduler, key-pairing
proof, or retention/deletion policy is introduced. These remain operator gates.

## Current sensitive data, not historical assumptions

The current `query_history.py` migration 5 persists opted-in domain history in SQLite;
retention `0` means no automatic expiry. Earlier paragraphs in the historical
`services/dns/OPERATIONS.md` describe an older RAM-only release and are not the current
backup boundary. Treat database backups as private browsing-history data as well as
identity/session/token material. Clearing live rows does not erase older backups.
Owner-approved backup access, encryption, expiration/deletion, and legal retention
rules need to cover these copies. Do not change a user's consent or retention setting
as a side effect of recovery.

## Why multiple workers/replicas remain blocked

- `app.buckets`: process-local IP admission buckets
- `management.account_buckets` and pending counters: account limits and buffered usage
- `moddns_adapter.account_locks`: policy mutation/recovery serialization; these locks
  do not coordinate two processes
- `query_history.preferences`, epochs, pending writes and locks: local coordination of
  consent, clear/disable, and in-flight records, even though history now persists
- Status/flush/probe state and cached policy timing are local; a restored SQLite file
  does not supply distributed locking or synchronized revocation

Before any scaling proposal: design shared atomic quotas, cross-process revocation and
consent invalidation, coordinated policy/recovery locks, durable counter behavior, and
multi-process race/failure tests. Rehearse compatible SQLite plus remote-backend
restore and fail-closed recovery first. Keep the Dockerfile's `--workers 1`; no Compose
replica count is added here. An independent monitoring location is not a DNS replica.

## Rollback and failure response

This is additive tooling, with no schema migration or runtime hook. Revert these files
for code rollback; no data restore is needed. A failed drill must stop the recovery
plan and preserve its sanitized reason for investigation. Never overwrite the live
database with an old backup merely to roll back code: it can resurrect revoked tokens,
re-enable disabled state, or undo consent/deletions. Preserve the live state and obtain
an explicit owner-approved incident recovery plan before any production action.
