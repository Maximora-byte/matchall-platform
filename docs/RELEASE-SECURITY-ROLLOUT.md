# Coordinated Hub and Mirrors release-security rollout

This is an owner-reviewed deployment plan, not deployment authorization. Deploy
Hub and Mirrors from the same reviewed PR #3 revision in one coordinated release.
The revision includes main's PR #12 payment guards and additive
`orders.stripe_session_id` migration; see [payment operations](../services/mirrors/PAYMENTS.md).

## Compatibility and order

- Hub still authenticates the exact request bytes before parsing. Missing/blank
  event secrets return 503; invalid signatures return 403. Validly signed invalid
  JSON, non-object bodies, missing/invalid `id` or `title`, and wrong types for
  consumed optional string fields return a fixed 400 without publishing. Parser
  size/depth errors and lone surrogate characters in consumed fields also return 400.
- Existing minimal events with nonempty string `id` and `title` remain valid.
  Optional defaults and extra Mirrors fields are preserved. `users` / `public`
  remain the only broad audiences. Explicitly private releases are rejected.
- New Mirrors sends public releases to Hub with explicit visibility and keeps
  private releases on their existing project-scoped webhooks only. Old Mirrors
  may send private releases as broad `users` events without visibility, which Hub
  cannot safely distinguish from legitimate legacy events. Do not leave this
  mixed-version combination running during rollout.
- Before any separately approved deployment, back up operational data and pause
  release publication/approval and event dispatch. Update Hub and Mirrors together
  while these paths are paused. If service starts must be sequential, start Hub,
  then Mirrors, and keep publication/dispatch paused until both are healthy and
  their revisions match. Do not resume after updating only one service.
- In the owner's authorized staging environment, check a public release reaches
  the intended Hub audience, a private release never reaches Hub, valid signatures
  still work, invalid signed payloads return 400 without notifications/jobs, and
  the payment acceptance/retry checks in `PAYMENTS.md` pass. Only then resume the
  coordinated release after the owner's production approval.

## Rollback and limits

Prefer a forward fix. If an owner approves rollback, pause the same publication
and dispatch paths, roll back Hub and Mirrors as a coordinated pair, verify both,
and resume only after reviewing the restored privacy/upload risk. Do not roll
Mirrors back to code that loses PR #12 payment checks. Leave its additive session
column, receipts, order history and entitlements intact; no database deletion or
schema downgrade is required for PR #3's event/upload changes.

Download readers continue to use stored artifact paths. Reverting upload writers
or event guards reintroduces their old risks. Existing overwritten bytes and
historical private notifications cannot be repaired by this change; do not delete
artifacts by display filename/version or purge notifications to force retries.
No production deployment, rollback, payment, notification or cleanup is performed
by this repository change.
