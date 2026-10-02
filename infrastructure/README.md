# Infrastructure references

Only sanitized examples belong here. Production Compose files, Caddy routes,
host inventories, credentials, database volumes, certificates, and backup data
remain outside Git.

Any future deployment automation must require an explicit environment and a
manual production approval. It must default to a local or staging target.

Optional external probe schedules, freshness checks, and the operator-owned alert
adapter contract are documented in [monitoring/README.md](monitoring/README.md).
These examples require review and separate activation on an independent host.

## Hub snapshot freshness override

`compose.hub.example.yaml` explicitly pins Hub's display freshness budget to
`"900"` seconds. This repository does not contain the operator's base Hub Compose
file. The example is an override only: first change its `hub` service key to match
the real base file, then apply it after that file. For example, validate the merged
configuration locally (this command does not start or deploy services):

```sh
docker compose -f /path/to/operator/hub-compose.yaml \
  -f /path/to/repository/infrastructure/compose.hub.example.yaml config --quiet
```

Keep the operator's base file and any expanded configuration containing secrets
outside Git. Use the same ordered `-f` arguments only for a separately authorized
deployment. Verify the collector schedule before choosing a different positive
integer budget; see [Hub snapshot semantics](../services/hub/CONSOLE_SNAPSHOTS.md).
