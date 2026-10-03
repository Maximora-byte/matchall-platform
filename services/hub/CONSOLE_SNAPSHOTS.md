# Console read-only summaries

Console reads only the existing `xboard.json`, `nextcloud.json`, and
`mirrors.json` files from the read-only snapshot mount. It does not run the
collector, query service databases, write service state, or add a DNS identity
adapter. DNS links use the existing `/login` and `/guide` routes. Do not put
personal DNS addresses or tokens into snapshots.

## State contract

- `linked`: a fresh, readable snapshot contains a matching, complete record.
  This says nothing about health, subscription validity, or paid access.
- `unlinked`: a fresh, readable snapshot contains no matching record. It does
  not mean the service is unavailable or promise automatic account activation.
- `restricted`: a fresh record explicitly reports Drive disabled or Network
  banned. Current permissions remain the original service's responsibility.
- `missing`: no snapshot is available; account linkage is unknown.
- `error`: unreadable/invalid JSON, invalid schema/timestamp, or an incomplete
  record, including an explicit collector failure. Error details and filesystem
  paths are never shown. A failed attempt does not advance the success timestamp.
- `stale`: the last snapshot is older than the configured freshness budget.
  A stopped collector or an output filesystem that cannot replace a snapshot
  can still leave the previous file to expire; freshness remains necessary.
- DNS `not-integrated`: a native service entry only, with no account status or
  synchronization time claimed.

A refresh reads existing files, not live data, and never advances snapshot time.
The overview counts each source separately; one missing source cannot be hidden
by the other sources' timestamps. Stale/error records are not displayed as current
usage. Existing subject/username/email matching rules are unchanged. Authenticated
Console responses are `private, no-store`.

## Deployment and rollback

No database migration is required. Successful collection preserves the legacy
`{"generated_at": <unix seconds>, "users": [...]}` schema exactly. Files are UTF-8.
The existing Network collector may emit explicit `null` for `online_count`;
Console preserves the legacy zero display for that value. Missing fields,
non-integer values, booleans, and negative counts still produce an error state.
`SNAPSHOT_STALE_AFTER_SECONDS` defaults to **900 seconds** when absent. A supplied
value must parse as a positive integer (`>= 1`); empty, non-integer, zero, and
negative values stop Hub at startup with a sanitized error naming the setting and
accepted range. Values are never silently clamped. There is no additional upper
limit, preserving existing positive integer configurations.

The [Hub-only Compose override example](../../infrastructure/compose.hub.example.yaml)
pins the value explicitly to `"900"`; apply it after the operator's real base Hub
Compose file using the [infrastructure instructions](../../infrastructure/README.md).
This is a display freshness budget, not a claim about the production collector
cadence. The owner must verify the actual schedule and mount permissions before
deployment and set an appropriate positive value. Missing/failing collectors need
operator action; there is deliberately no web-triggered collector or sync button.

Deploy only after explicit owner review/approval. Roll back the Hub code, template,
and CSS together; no business-data rollback is needed. This change does not deploy
or alter DNS routes, accounts, credentials, subscriptions, or filtering.

## Independent source collection

`snapshot.py` remains an operator-run host process, separate from Hub's web
requests. It collects Network, Mirrors, and Drive in order, each with its own
monotonic time budget. A timeout or other exception in one source does not stop
the remaining sources. A snapshot is published only after that source completes;
if a command fails while processing the returned Drive user batch, no partial
batch is published. Missing/invalid enabled, used, or quota fields fail instead
of fabricating an enabled account with zero usage. Both `{}` and `[]` are accepted
as empty CLI user listings. Imports do not start collection.

The existing `user:list` pagination behavior is unchanged (current upstream
defaults to a 500-user limit). This change does not prove full account enumeration
beyond that returned batch. Operators must check their deployed Nextcloud version
and user count; pagination coverage needs a separate change before relying on
this collector for a larger directory.

The defaults are 120 seconds per source and 15 seconds per Docker client command.
Operators can tune `--source-timeout` (integer 1-900 seconds) and
`--command-timeout` (integer 1-120 seconds); each command uses the smaller of its
limit and the remaining source budget. Invalid limits fail before collection.
These are collection budgets, separate from `SNAPSHOT_STALE_AFTER_SECONDS`.

SQLite sources open in read-only mode, so missing source paths fail without
creating databases. Backup progress checks include busy/locked retries; query
progress and row conversion also check the deadline. Temporary copies and
connections are cleaned up on normal completion and exceptions. These deadlines
are cooperative for SQLite/Python work, not hard limits on stalled kernel disk
I/O or atomic-file publication. A Docker-client timeout terminates and waits for
that client, but does not prove that Docker stopped the PHP process in the
container. Operators must prevent overlapping collector runs and review remote
process behavior before choosing the schedule or increasing limits.

Failures atomically replace only the affected source's file with:

```json
{"generated_at":null,"users":[],"collection_state":"error","attempted_at":2000000000,"error_code":"collection_timeout"}
```

The only error codes written by the collector are `collection_timeout`,
`collection_failed`, and `publication_failed`. The failure envelope contains no
account records, raw commands, paths, command output, or exception messages.
`attempted_at` is diagnostic metadata, never a successful refresh time. Current
Hub explicitly rejects any `collection_state` marker; older Hub also displays
these failures as errors because `generated_at` is null. A successful retry
replaces the whole file with the legacy success payload and removes the marker.
Identity matching and the source permission/ownership requirements are unchanged.

If output publication fails, the collector attempts a small sanitized failure
envelope and continues other sources. Persistent filesystem failure can prevent
even that write: the old file may remain current until its original timestamp
expires. It must not be described as immediate failure visibility in that case.
The CLI emits one sanitized JSON summary (source names, states and fixed codes)
and exits 0 only when all three sources collect and publish successfully; any
source/publication failure exits 1, invalid arguments exit 2. Its exit status
requires operator monitoring; this change does not configure a scheduler or alert.

Deploy the collector only after owner review of host paths, its existing output
ownership (UID/GID 10001), command access and non-overlapping schedule. The success
format and fail-closed envelope allow either Hub/collector rollout order. To roll
back, restore the previous collector and/or Hub code; no source database or user
record restoration is needed. Old collectors will again leave previous snapshots
on failure, so retain freshness checks and supervise the collector's exit status.

## Offline verification

Install `requirements.txt`; run each `test_*.py` in its own Python process. Tests
use temporary synthetic SQLite databases/snapshots and mocked Docker commands.
They do not enter the application lifespan, invoke collection against the default
operational sources, or contact real services. Collector tests mock ownership
changes; actual UID/GID/mount permissions and deployed schedules remain operator
acceptance items. No live collection or deployment is authorized by these tests.
