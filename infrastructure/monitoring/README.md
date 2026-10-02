# Optional external monitor activation

These Linux/systemd examples are not installed or enabled by a repository change.
Use a separately hosted operator-approved machine outside the primary fault domain.
Its location, networking and alert delivery must be verified; all reports retain
`operator_managed_unverified` and `business_availability: not_verified`.

## Operator prerequisites

Review the paths and service account in all four unit files. Provision an unprivileged
`matchall-monitor` account, install a reviewed revision at
`/opt/matchall-monitor/repository`, and install Hub requirements into the referenced
virtual environment. Copy the credential-free probe configuration from the Hub
example to the operator-owned `/etc/matchall-monitor/probes.json`, replacing placeholders
only with approved public HTTPS endpoints. Do not use real account tokens or headers.
Nothing here requires another DNS worker or replica.

The runner finishes with a bounded, sanitized mode-0600 state file. Its whole-cycle
deadline is 220 seconds (up to 20 ten-second probes); the next run starts 60 seconds
after the previous one finishes. The separately scheduled watchdog checks every
60 seconds and rejects reports older than 300 seconds. Missing/invalid/future-dated
state, failed probes, configuration/runner errors and timeouts are unhealthy.
An initial missing report is unhealthy until the first cycle completes.
Do not enlarge the cycle deadline/interval beyond the freshness budget without
reviewing the relationship; synchronize the monitor's clock.

## Alert adapter contract

Provide an absolute, operator-owned executable at
`/usr/local/libexec/matchall-monitor-alert`. It receives one sanitized JSON event on
stdin (reason, observed time, coverage labels), receives no shell arguments, and
must complete in 15 seconds. Exit 0 acknowledges acceptance; nonzero/timeout/missing
adapter is reported as failed. Stdout/stderr are suppressed to avoid disclosing
notification configuration. The adapter must implement the authorized delivery
method and keep credentials outside Git. A zero exit is adapter acknowledgment,
not proof that a human received a message.

The watchdog sends on every unhealthy check; configure deduplication/rate limiting
in the adapter. It exits nonzero even when the alert is accepted. Successful fresh
checks send no message. Recovery notifications are not implemented. Both timers
must be enabled together after review; a probe timer alone has no missed-run alert.

Review syntax without starting services:

```sh
systemd-analyze verify infrastructure/monitoring/*.service infrastructure/monitoring/*.timer
```

For local acceptance, use synthetic configuration/results and an adapter that writes
stdin to a temporary file, as in `services/hub/test_probe_watchdog.py`. Do not run
the example against production to test it.

## Deployment acceptance still required

Record independent host/network evidence and actual successful alert delivery,
then test an authorized synthetic failure, runner timeout, disabled probe timer
(watchdog left active), stale report, adapter failure and recovery. A stopped primary
host must be observable from the second location. If the entire second monitor host
or its watchdog stops, local timers cannot detect that failure; an independently
operated dead-man receiver is a separate deployment requirement.

No report ingestion into Hub/public status is introduced. A consumer must apply the
same missing/stale rules before displaying these results and preserve coverage labels.
This is an opt-in operational scaffold, not a claim of monitored production availability.
Rollback: disable/remove these optional units and revert the watchdog code, leaving
DNS routing, user data and existing Hub history unchanged.
