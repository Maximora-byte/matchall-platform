# Monitoring scope and operator activation gates

This change supplies code and mocked tests. It does **not** deploy a second probe
location, schedule an external runner, create accounts, change routing, or establish
production availability. The examples use placeholder hosts and must not be treated
as a configured service.

## Three separate questions

- `GET /healthz`: the Hub process can answer HTTP. Its existing response is unchanged.
- `GET /readyz`: HTTP 200 only when both background tasks are running, their progress
  is recent (180 seconds), configured probe settings are valid, and both local
  database schemas can be read. Otherwise HTTP 503 with fixed reason codes and
  `Cache-Control: no-store`. It does not test database writes, SMTP/push delivery,
  upstream business success, failover, or external reachability. Initial readiness
  stays 503 until the first complete probe cycle and first delivery-loop iteration.
- `GET /api/status`: the observed service checks, including stale/missing results.
  `coverage_level`, `configuration_state`, `configured`, and
  `business_availability` are additive schema-v2 fields. All current probes explicitly
  report `business_availability: not_verified`. A successful liveness check cannot
  establish successful login, file transfer, purchase, or account DNS policy.

The delivery heartbeat measures job-loop progress, not successful delivery. The
probe heartbeat updates after a full persisted cycle, even if an upstream is down:
healthy monitoring and healthy upstream services are different conditions. A cycle
exception is visible immediately through `/readyz` and retried next interval. A
stopped or stalled task cannot remain ready. Shutdown cancels and awaits tasks.
These are process-local checks; do not add workers to make them appear redundant.

## Explicit DNS resolution monitoring

Hub adds the `dns` service as **unknown/unconfigured** by default; it makes no request
and records no failed sample until both settings are supplied:

| Environment variable | Purpose |
| --- | --- |
| `MONITOR_DNS_DOH_URL` | Explicit HTTPS public resolver URL ending exactly `/dns-query` |
| `MONITOR_DNS_DOMAIN` | Operator-selected public DNS name for an A query |
| `MONITOR_DNS_EXPECTED_ADDRESSES` | Optional comma-separated IPv4 allowlist; every returned A address must belong to it |

Probe configuration comes from trusted administrators (Hub environment settings or
an operator-managed local runner file), not anonymous URL input. Administrators must
select trusted, credential-free **public HTTPS endpoints**. `validate_public_url`
checks URL syntax only: it does not resolve or enforce public destination IPs, block
private/loopback addresses, or prevent DNS rebinding. It is not an SSRF protection
boundary for untrusted input. Endpoint ownership and DNS/network trust remain the
administrator's responsibility; do not expose these settings to untrusted users.

URLs with credentials, query strings, fragments, non-443 ports, or HTTP are rejected;
the DNS resolver additionally requires the exact `/dns-query` path. Syntax validation
cannot identify secrets in arbitrary runner URL paths, so administrators must not
configure token-bearing paths. Partial/invalid configuration remains unknown and
makes Hub readiness fail. Removing configuration makes the service unknown even if old samples
exist. Unconfigured DNS means the overall status is not fully operational; this is an
intentional indication of missing coverage, not a DNS outage.

The probe checks HTTPS status/content type, DNS transaction/question correspondence,
an untruncated response, NOERROR, a nonempty A answer for the queried name (following CNAMEs), and the optional
address allowlist. NXDOMAIN, SERVFAIL, empty or wrong answers, redirects, malformed or
oversized responses, and timeouts fail. Without an address allowlist it verifies a
matching DNS answer, not that an address is the intended deployment. Choose a stable,
operator-controlled record if exact-address validation is required. DNSSEC validation,
AAAA/IPv6, DoT/DoQ, filtering, token revocation, and account gateway success are not
covered. This monitor never provisions a synthetic or real account.

Checks use only GET, TLS verification, no environment proxy, no cookies between
checks, and no redirects. They have an 8-second I/O timeout and a 10-second whole-probe
deadline. Requests send `Accept-Encoding: identity`; non-identity `Content-Encoding`
responses fail before reading or decompressing their bodies, even if the server ignores
that request header. Semantic bodies are read as raw bytes and capped at 65,535 bytes
before accumulation (not after HTTPX decompression). Header-only reachability checks
still do not read bodies. Only fixed reason codes are stored; public status never
exposes resolver configuration, query names, raw responses,
or transport exception text.

## Read-only business-contract scaffold

The Drive public `status.php` probe now requires boolean `installed=true`,
`maintenance=false`, and `needsDbUpgrade=false`. HTTP 200 alone is insufficient.
This detects maintenance/schema-upgrade states while making no user-data writes.
Account/Mirrors remain labelled liveness; static pages/network remain reachability.
The reusable probe runner supports reachability, this Nextcloud contract, Hub readiness,
and DNS resolution only. Full login/upload/download/subscription/purchase scenarios
need a separate owner-approved test identity and bounded workflow; they are not
fabricated by this change.

## Optional independently located runner (not deployed)

`services/hub/probe_runner.py` imports only probe code; it does not import Hub, read
secret files, create a database, submit notifications, or register persistent access.
It runs once and writes a bounded sanitized JSON report to stdout. Exit codes: 0 all
checks pass, 1 a check fails, 2 invalid/missing local configuration. The report labels
its vantage point `operator_managed_unverified`: a label alone cannot prove independence.

Before running against approved endpoints, the operator must:

1. Select a separately hosted machine and network outside the Hub/DNS fault domain;
   approve its resources, public destinations, and a credential-free configuration
2. Install the Hub requirements in that environment and replace placeholder hosts in
   `services/hub/examples/external-probes.json`; never use token-bearing URLs or headers
3. Run from `services/hub`: `python probe_runner.py --config /approved/local/probes.json`
4. Configure scheduling and alert delivery separately, including alerting on a missed
   run/old report. Verify resolver failure, Hub task failure, and total primary-host
   outage from that actual second location. Do not let the primary host be the sole
   report store or notification sender

Optional Linux/systemd scheduling and a bounded watchdog are now provided in
[`infrastructure/monitoring`](../infrastructure/monitoring/README.md). The watchdog
atomically stores a sanitized cycle result and checks missing/stale/failed reports
on a separate timer. An operator-supplied executable receives sanitized JSON alerts
with a bounded timeout; acknowledgment and actual delivery remain separate gates.
These examples install/enable nothing. No alert receiver, external infrastructure,
or status-feed ingestion is created here. An external runner installed on the same
host is **not** independent.
Do not point a restart policy at upstream business-status failures; monitor `/readyz`
for Hub-local trouble and the external report for externally observed availability.

## Verification, migration, and rollback

`services/hub/test_monitoring.py` uses HTTP/DNS mocks and temporary SQLite databases;
no production hosts or accounts are contacted. Existing service tests run in separate
Python processes. There is no database migration. Rollback is a code-only revert and
removal of optional DNS environment settings; retain existing status history. Owner
review is required because the observable DNS/status semantics change. Deployment,
external-location proof, alert delivery, and real business acceptance remain operator
gates after review; a green PR does not satisfy them.
