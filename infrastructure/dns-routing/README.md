# CN routing health report ownership and migration

The routing health publisher is now owned by this repository at
[`services/dns/routing_health.py`](../../services/dns/routing_health.py), with
deterministic tests in `services/dns/test_routing_health.py`. It uses Python's
standard library and does not start with the DNS web application.

The deployed operational script reported in issue #56 was outside the tracked
tree. This is a replacement for its **check orchestration and report publication**,
not a copy of production configuration or evidence of a production fix. The
operator must review and adapt the existing read-only checks to the exit-code
contract below; their endpoints, tunnel peers and credentials remain outside Git.
The example executable is a placeholder and is not provided or installed here.
Do not treat a passing repository test as verification of those external probes.

## Required probe contract

`checks.example.json` lists every required check. An operator-owned, trusted
configuration must supply all six identifiers exactly once, with an absolute
executable and an argument list. No shell is invoked. Each probe must return 0
only after its entire assertion passes, and nonzero on unavailable, malformed,
missing or unexpected data. A probe must not return success merely because a
transport command completed. A missing executable, nonzero exit or timeout is a
failed check; the other checks still run.

| Identifier | Required assertion |
| --- | --- |
| `global_backend` | The required Global backend is available. |
| `cn_backend` | The CN backend/pool satisfies the owner's explicitly reviewed availability/redundancy policy. Global fallback does not satisfy this check. |
| `tunnel_fresh` | The required tunnel peer has a nonzero, non-future handshake within the owner's maximum age. |
| `dns_global` | A synthetic query through the actual Global path returns the expected DNS response and answer. |
| `dns_cn` | A synthetic query through the actual CN path returns the expected response and answer, using the approved CN provider DNSSEC policy. Fallback must not disguise the path being tested. |
| `dnssec` | Global's strict validation assertions all pass, including valid signed results and rejection of bogus signatures. |

CN provider policy differs from Global's local root-trust validation; this contract
does not require CN public providers to implement Global's exact AD/bogus policy.
The owner must specify the synthetic assertions and the CN pool redundancy policy
before activation. The script cannot infer either from a backend's exit code.

Probes receive no stdin. Their stdout/stderr are discarded, and no command,
endpoint, query name, peer, exception text or raw output enters the report. Keep
secrets out of command arguments and load necessary private configuration in the
operator-owned probe. Use only read-only probes; no restart, routing update or
other mutation belongs in a check. Keep probes single-process or have them `exec`
their final command so timeout termination does not leave detached workers.

## Report and consumer contract

Each serialized cycle first atomically replaces the old report with
`healthy: false`, `reason: checks_pending`. This happens before loading config or
running any probe, so an early failure cannot leave the previous success visible.
The final report is atomically replaced after **all** checks, with `healthy`
derived from their conjunction. Failed check names come only from the fixed
identifier list. Missing/invalid configuration writes a fresh false report with
`reason: configuration_invalid`. Exit 0 means all checks passed; exit 1 means
the published report is unhealthy. Publication/lock errors exit 2 with a fixed
sanitized error, and must be handled as operational failures.

`global_up` and `cn_up` are integer 0/1 backend observations. Separately,
`global_fallback_available` requires `global_backend`, `dns_global` and `dnssec`.
CN or tunnel failure can leave Global fallback available while overall
`healthy` is false. A fallback-only success must never be displayed as full CN
routing health.

`schema_version: 1` reports contain the epoch-second **cycle start** in
`checked_at`, a Boolean result for every check, `failed_checks`, and a fixed
`reason`. These fields replace the legacy unconditional Boolean contract.
Consumers must use `routing_health.inspect()` or the `check` command below before
displaying results. They reject missing, malformed, oversized, future-dated,
inconsistent and older-than-300-second reports. A stricter age budget is allowed;
raising it above 300 seconds is rejected. Rejected reports expose neither healthy
CN routing nor available fallback. Unknown report fields are never relayed.

The per-probe timeout defaults to 5 seconds and is restricted to 1..10, bounding
the six-probe work to 60 seconds plus local I/O. Writers share an OS-held lock;
an overlapping invocation fails without overwriting the active writer's report.
The temporary report lives beside its destination, is flushed, and is replaced
on the same filesystem. Store report/config/lock files in a trusted local
directory. The immediate report directory and new report/lock files are private
(0700/0600 on Linux); provision any parent directories with suitable permissions.
An authorized consumer needs access through the same account or an explicitly
reviewed read-only mechanism.

If the process is killed after it begins, its pending false report remains.
If it never starts, cannot acquire the lock, or cannot write, an existing report
can survive until its freshness deadline. Therefore **every consumer** must apply
expiry even when a scheduler normally runs successfully. Service errors also need
the operator's existing local monitoring; no notification adapter is added here.

## Owner-reviewed activation only

1. Review this publisher and the external probe implementations. Keep the real
   configuration outside Git; adapt the placeholders in `checks.example.json`
   locally. Do not fetch production scripts or private configuration into Git.
2. On an isolated host, exercise synthetic success, CN outage, early probe failure,
   timeout, missing configuration and stopped-scheduler/expired-report cases.
   Verify the report and service result together, and preserve Global fallback
   separately during a CN-only failure.
3. Obtain explicit `@Maximora-byte` review for the DNS routing/report semantics.
   Production activation requires separate approval. In the existing oneshot
   health service, replace the old early `printf`/`mv` and trailing `test` flow
   with one invocation of this publisher. Retain the service's nonzero result.
4. Update every routing-report consumer to the new schema and mandatory freshness
   check in the same approved change. Do not point the DNS portal's unrelated
   `DNS_HOST_HEALTH_FILE` backup/disk/certificate reader at this routing report.

Illustrative invocations using operator paths (not deployment commands):

```sh
python3 /opt/matchall/repository/services/dns/routing_health.py run \
  --config /etc/matchall/routing-checks.json \
  --report /run/matchall-routing/health.json

python3 /opt/matchall/repository/services/dns/routing_health.py check \
  --report /run/matchall-routing/health.json --max-age 300
```

Schedule serialized runs no more than 60 seconds apart after completion, and
retain a service deadline above the six-probe budget but below the consumer's
freshness budget. A merge does not install, schedule or deploy this implementation.
Rollback removes the publisher invocation and its consumer integration together;
keep the failed/stale-report handling and do not restore unconditional success.
There is no database migration, resolver policy update or traffic change.
