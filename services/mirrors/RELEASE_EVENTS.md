# Durable release notifications

Owner approval saves `release.published` tasks in `release_event_outbox` in the
same SQLite transaction as the release status and audit entry. If any part fails,
approval rolls back. The response returns after that transaction; network delivery
runs in a separate application-lifespan worker, checking for work every 5 seconds.
Only developer owner approval queues these events. Existing administrator release
creation and GitHub synchronization do not gain new notification behavior, and
historical releases are not backfilled.

## Delivery contract

Each event/destination pair is unique. The JSON bytes and existing event ID
`release:{slug}:{channel}:{version}` stay fixed across retries. A project with
public visibility queues a Hub notification and its active project webhooks
subscribed to `release.published`; a private project queues only its own active,
subscribed webhooks. A missing Hub signing secret
is a delivery failure that can recover on a later attempt.

The worker claims one due task atomically, using a random claim token and a
60-second lease. Network requests happen outside the database transaction. A
restart or cancellation leaves the claim recoverable after its lease expires.
Updates from an obsolete claimant cannot overwrite a newer claim. Multiple
workers may run against the same local SQLite database.

Each task has at most 8 attempts, including claims interrupted by a process exit.
Failed attempts wait 30, 60, 120, 240, 480, 960 and 1920 seconds before the next
attempt; the backoff is capped at 3600 seconds. HTTP 2xx is delivered; other HTTP
statuses, network failures and unavailable signing configuration retry up to the
limit. Exhaustion leaves a `failed` row for owner investigation. It does not retry
forever, configure alerts, or provide an automatic/manual retry web endpoint.

HTTP requests disable redirects and use an 8-second client timeout within a
10-second overall attempt limit. External webhook URLs are checked again
before each attempt, including DNS address checks. DNS validation has a separate
bounded wait; an expired wait does not guarantee cancellation of its resolver
thread, and asynchronous limits cannot force-stop synchronous SQLite disk I/O.
These checks retain the existing validator and do not pin the HTTP
connection to its checked DNS address, so they are not a complete DNS-rebinding
defense. The Hub destination remains trusted operator configuration.

Before sending, the worker checks that the release is still published and the
project visibility still agrees with the queued payload. Rollback, redrafting or
visibility changes cancel pending delivery. A Hub attempt additionally requires a
currently public project. Project hooks must remain active and belong to the
same project and still subscribe to `release.published`; the prior one-shot
sender ignored the subscription field. Deleting a release,
project or hook removes its dependent tasks.
State changes cannot recall notifications already received, and a state change
after the final check can race an in-flight request.

Delivery is **at least once**. A receiver may accept a request before its response
is lost or the sender exits. The retry uses the same event ID; receivers must
deduplicate on that ID. Hub already deduplicates its notification event key.
Reapproving the same slug/channel/version uses the same logical event ID and
does not queue another task for destinations that still have an outbox row.

## Security, storage and observation

Outbox payloads contain existing release metadata: project slug/name, version,
channel, visibility, audience, title, body, project URL and publication time.
They contain no user identity, artifact bytes, download token or signing secret.
Hub secrets are read from the existing secret file and webhook secrets from the
existing hook record at each attempt. Signatures cover the stored bytes.

Delivered and cancelled tasks erase their stored payload. Pending, processing
and failed tasks retain it for recovery/investigation; metadata rows remain
until their parent is deleted or an owner performs approved cleanup. There is no
new timed retention or cleanup job. Private release metadata is now persisted
in this queue, so explicit owner review of privacy and retention is required.

Task state, attempt count, next-attempt time, lease, HTTP status and fixed error
codes are available in the outbox. Project webhook attempt history continues in
`webhook_deliveries`; response bodies, URLs, secrets and raw exception messages
are not written as errors. A worker/database failure emits a fixed diagnostic
message without those details. Operators must monitor failed rows, pending age
and the worker; the existing HTTP health check does not establish delivery health.

## Migration, rollout and rollback

Startup adds only the outbox table and indexes, idempotently. Existing releases,
webhook history, authentication, payment records and download permissions do not
require a data migration. The normal Mirrors Dockerfile includes the new module;
build the application image before an approved rollout. Template-only legacy
Dockerfile variants do not include this code upgrade.

The owner must review the additive schema, outbound destinations, signing
configuration, network restrictions, queue retention and monitoring before
deployment. Tests do not authorize production access, merge or deployment.

For rollback, stop the new application workers before restoring the prior code
and image. The older application ignores the additive table; retain it so queued
work can resume after a corrected upgrade. Old code returns to one-shot delivery,
so events approved while running old code are not added to the durable queue.
Do not drop the queue or rewrite business data as part of a code rollback.

## Offline verification

Install `requirements.txt`, then run each `test_*.py` in a separate Python process.
Tests use temporary synthetic databases, mocked HTTP/DNS/signing configuration
and mocked lifespan work. They verify commit/rollback, retry and restart recovery,
leases, duplicate suppression, signatures and visibility controls without real
service connections. Actual host permissions, outbound networks, receiver
deduplication and operational monitoring remain owner acceptance items.
