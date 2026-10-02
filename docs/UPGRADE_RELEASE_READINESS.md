# Upgrade review and release acceptance

Evidence reviewed: 2026-10-03 (Asia/Shanghai).
Repository base: `f44c73daab6775054510c5c4148dbd70860e21cf`.

This checklist connects the homepage, Console reliability, Mirrors delivery,
and shared-guide upgrades. It records reviewable repository evidence and
remaining operator work. It does not authorize merging or deployment. No
production infrastructure, real account data, or external receiver was used
for this review. PR state and CI links below are a dated snapshot; recheck them
after any revision or base change.

## Reviewed batch and integration order

| Order | Scope | Reviewed head | Passing CI |
| --- | --- | --- | --- |
| 1 | [#58: homepage onboarding](https://github.com/Maximora-byte/matchall-platform/pull/58) | `54d41f104dd830a785b0ab58f99f4f918468b50d` | [run 37020699875](https://github.com/Maximora-byte/matchall-platform/actions/runs/37020699875) |
| 2 | [#59: Hub snapshot isolation](https://github.com/Maximora-byte/matchall-platform/pull/59) | `19401ec7bb2114af9452000b9f473365ec92d7e0` | [run 37024092687](https://github.com/Maximora-byte/matchall-platform/actions/runs/37024092687) |
| 3 | [#60: Mirrors event outbox](https://github.com/Maximora-byte/matchall-platform/pull/60) | `dcb83b0a980289c6ca1bfc6563beb73bda83f012` | [run 37025574252](https://github.com/Maximora-byte/matchall-platform/actions/runs/37025574252) |
| 4 | [#61: shared service guides](https://github.com/Maximora-byte/matchall-platform/pull/61) | `2b5e298b006d71316750da72c68b6974bdcbc736` | [run 37027777834](https://github.com/Maximora-byte/matchall-platform/actions/runs/37027777834) |

All four PRs were open and unmerged when reviewed. This order groups the user
journey before the supporting reliability and documentation work; it is not a
hard dependency chain. The guides describe version-dependent delivery, so #61
can merge before #60 without claiming that retries are already deployed.

Local `git merge-tree --write-tree` simulations combined those exact heads in
order against the base above without conflicts. Temporary commit objects were
used only to carry each simulated tree forward; no branch or main history was
merged. This proves textual merge compatibility, not combined runtime behavior.

Before integration approval, review each diff and recheck its CI at the final
head. Changes to account-summary handling need owner review; #60 explicitly
requires privacy/data-retention review under [AGENTS.md](../AGENTS.md). Any DNS,
authentication, payment, download, or retention change also requires explicit
owner review. Preserve the existing route boundaries in the
[roadmap](../apps/main-site/MIGRATION_ROADMAP.md).

After integration, run the affected checks on the combined revision: `npm ci`,
`npm run check`, and `npm run build` for the main and documentation apps; main
unit/browser regressions; Fuwari's frozen pnpm install, check, and build; and
each Hub and Mirrors `test_*.py` in a separate Python process after installing
their requirements. Run `python scripts/sync_guides.py` once #61 is present.
Record that combined revision and results; individual PR checks do not replace
this gate.

## Acceptance in a separately approved environment

Use synthetic accounts, release metadata, snapshots, and operator-controlled
test receivers. Record sanitized outcomes, not raw user data, response bodies,
secrets, or production logs. These checks are pending until an owner records
actual evidence for the deployed revision.

### Homepage and guides (#58, #61)

- Verify desktop and narrow mobile navigation, keyboard access, visible sign-in,
  and the sign-in link with JavaScript disabled. Confirm invitation wording does
  not imply unrestricted self-service registration.
- Follow getting-started, DNS, Drive, Network, Mirrors user, and Mirrors
  developer guides through the documentation and blog entries. Keep existing
  guide URLs and the documentation feedback endpoint working.
- Verify the existing login handoff and expired/cancelled-session recovery with
  synthetic accounts. No new identity-provider flow is introduced by this batch.
- Check the documentation sync in read-only mode and confirm one page title and
  one native feedback control per rendered guide.

### Console snapshot collection (#59)

- Validate collector mounts, read-only source access, output ownership/mode, and
  a schedule that prevents overlapping runs. The defaults are a 120-second
  budget per source and a 15-second Docker-client timeout.
- With fixtures, make one source fail or stall. Other sources must still run;
  the failed source must publish a sanitized error envelope without user rows
  or a successful timestamp. Collection failure must produce a nonzero exit.
- Restore the source and confirm its next successful snapshot recovers in
  Console. Verify stale data is labelled correctly; the default display budget
  is 900 seconds, not evidence of an installed collection schedule.
- Verify the deployed Nextcloud CLI schema, both supported empty-list formats,
  and atomic file publication. A publication/filesystem failure may leave an
  old file to expire. A Docker-client timeout does not prove termination of its
  remote PHP process; disk-I/O deadlines are cooperative.
- The unchanged Nextcloud listing has a default 500-user limit. Do not accept
  completeness for a larger directory without a separate pagination change.

Use [Console snapshot operations](../services/hub/CONSOLE_SNAPSHOTS.md) and the
reviewed #59 diff for the updated collector contract. Collector and Hub rollout
can occur in either order because older readers also reject the failure envelope.

### Mirrors durable events (#60)

- Review destinations, retained release metadata, and the new additive outbox
  table/index before approval. Pending/processing/failed payloads can include
  private project titles and versions. Delivered/cancelled payloads are cleared;
  failed rows and metadata have no timed cleanup. Confirm an operational owner
  for failed tasks; this PR adds no queue alert or replay UI.
- Build and start the candidate image in the approved test environment. Verify
  the new module is packaged and worker startup/shutdown works with the actual
  mount permissions. The earlier PR verified tests and packaging inspection,
  not image runtime acceptance.
- Publish synthetic public/private releases through owner approval. Publication,
  audit, and queued tasks must commit together. Private releases must never
  enqueue Hub events; only eligible project hooks may receive them.
- Make the test receiver unavailable, then recover or restart Mirrors. Confirm
  the same signed event bytes/ID survive recovery. Simulate a lost response and
  verify receiver deduplication: delivery is at least once, not exactly once.
- Confirm disabled hooks and unpublished releases cancel ineligible work, and
  deleted parent records remove dependent tasks. Exhausted tasks must remain
  failed after eight claims. A healthy HTTP endpoint
  or a successful enqueue does not prove delivery. Administratively published,
  GitHub-synchronized, and historical releases retain their existing behavior.

Use the operational contract introduced by #60 in
`services/mirrors/RELEASE_EVENTS.md` after integrating that PR. Existing URL
validation does not pin the later HTTP DNS address; the change is not a complete
DNS-rebinding defense. If upgrading from before the historical visibility/HMAC
security pair, also follow the
[coordinated security rollout](RELEASE-SECURITY-ROLLOUT.md); #60 alone does not
replace those protections.

## Existing reliability work still awaiting operational acceptance

- [DNS publisher #57](https://github.com/Maximora-byte/matchall-platform/pull/57)
  is merged and [issue #56](https://github.com/Maximora-byte/matchall-platform/issues/56)
  is closed for the code fix. Deployment acceptance remains unverified: adapt
  all six probes, validate the versioned report/freshness contract and global
  fallback, and rehearse missing, malformed,
  overdue, and all-unhealthy reports in an owner-approved environment. Use the
  [DNS examples](../infrastructure/dns-routing/README.md) and
  [recovery rehearsal](dns-recovery-rehearsal.md). Merge does not install a
  publisher, timer, or router configuration.
- [Monitoring issue #49](https://github.com/Maximora-byte/matchall-platform/issues/49)
  stays open until a separately located probe, scheduling, missed-run detection,
  actual notification delivery, and whole-monitor-host deadman detection are
  accepted. A same-host probe is not an independent fault domain. An adapter's
  exit code proves acceptance by that adapter, not receipt by an external person.
  See [monitoring readiness](monitoring-readiness.md) and
  [scheduler examples](../infrastructure/monitoring/README.md).
- Public Status freshness integration also remains pending under #49. Treat
  missing or overdue evidence as unknown/stale. `/healthz`, `/readyz`, and business
  checks have different meanings; do not present `not_verified` as healthy.

## Rollback and acceptance record

Revert homepage/guide presentation to the last approved revision while retaining
backend routes and feedback handling. For #59 restore the previous collector
and/or Hub; supervise failures because the old collector retains earlier files.
Neither change requires a source database rollback.

For #60, stop the new workers before restoring the previous application. Retain
the additive outbox table for a corrected upgrade; old code ignores its queued
work and resumes one-shot delivery. Approvals made during rollback are not
retrospectively queued. Do not erase application data or reverse the historical
security/payment fixes. DNS rollback follows its separate rehearsal document.

For each gate, record: reviewed and deployed revision, service, approving owner,
authorized environment, time/timezone, synthetic scenario, expected/actual
outcome, sanitized evidence reference, rollback result, and unresolved items.
Mark pending items explicitly. Close #49 only after its operational gates are
satisfied. The closed code issue #56 is not deployment evidence; record the DNS
rehearsal separately. Repository CI and merge simulations prove neither gate.
