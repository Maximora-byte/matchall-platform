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
  record. Error details and filesystem paths are never shown.
- `stale`: the last snapshot is older than the configured freshness budget.
  The collector currently leaves its previous snapshot on failure; therefore
  an old snapshot cannot distinguish a collector failure from a stopped job.
- DNS `not-integrated`: a native service entry only, with no account status or
  synchronization time claimed.

A refresh reads existing files, not live data, and never advances snapshot time.
The overview counts each source separately; one missing source cannot be hidden
by the other sources' timestamps. Stale/error records are not displayed as current
usage. Existing subject/username/email matching rules are unchanged. Authenticated
Console responses are `private, no-store`.

## Deployment and rollback

No database migration or collector format change is required. The legacy
`{"generated_at": <unix seconds>, "users": [...]}` schema remains supported.
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

## Offline verification

Install `requirements.txt`; run each `test_*.py` in its own Python process. Tests
use temporary snapshots and patched status data, do not enter the application
lifespan, and must not run `snapshot.py` or contact real services.
