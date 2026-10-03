# Site upgrade roadmap

Status reviewed: 2026-10-03 (Asia/Shanghai). This is a repository roadmap;
implementation, PR merge, and deployment acceptance are separate milestones.
See the [upgrade release checklist](../../docs/UPGRADE_RELEASE_READINESS.md) for
review order, evidence, acceptance criteria, and rollback.

## Implemented in the repository

- Main public site, policy pages, service entries, blog branding, and CV build
  pipeline.
- Documentation in Astro Starlight, the Status presentation shell, and the
  public Mirrors catalogue. APIs and stateful routes retain their backends.
- DNS public entry, Console entry and authenticated Hub summary, and Investment
  public pages. Their existence does not mean every authenticated view has been
  migrated or its deployment has been accepted.
- DNS health-report publisher and bounded recovery behavior (merged PR #57).
  Operator configuration, scheduling, and recovery acceptance remain separate.

The [2026-09-30 expansion report](ASTRO_EXPANSION_REPORT.md) records historical
work; it is not current deployment evidence.

## Current upgrade batch: integration and remaining acceptance

| Work | Review | Remaining acceptance |
| --- | --- | --- |
| Clear login/invitation guidance and visible mobile sign-in | [PR #58](https://github.com/Maximora-byte/matchall-platform/pull/58), merged | Deployed navigation and existing login flow |
| Independent, bounded Console snapshot collection | [PR #59](https://github.com/Maximora-byte/matchall-platform/pull/59), merged | Collector permissions, scheduling, deployed failure/recovery behavior |
| Durable Mirrors release-event retries | [PR #60](https://github.com/Maximora-byte/matchall-platform/pull/60) | Owner privacy/retention review, receiver deduplication, queue recovery |
| Six shared guides and clearer documentation entry | [PR #61](https://github.com/Maximora-byte/matchall-platform/pull/61), merged | Deployed URLs, feedback and service navigation |

Individual CI passed for the reviewed revisions. Combined local Hub/Mirrors,
main-site and blog checks now pass; Starlight's reviewed-head CI passed. The
release checklist records the exact source and local verification limit.
Operational acceptance remains separate. These PRs have not been deployed by this task.

## Next priorities

1. Complete #60's owner review and verify final-main CI after integration.
   Use the release checklist before any separately authorized rollout.
2. Complete independent probe, missed-run, notification-delivery, and whole-host
   deadman acceptance in [issue #49](https://github.com/Maximora-byte/matchall-platform/issues/49).
   A successful synthetic run is not proof of external notification delivery.
3. Validate DNS recovery using the new publisher contract and an owner-approved
   rehearsal. [Issue #56](https://github.com/Maximora-byte/matchall-platform/issues/56)
   is closed with an owner-recorded activation/acceptance result; further recovery
   rehearsals and the intermittent underlying CN network fault remain separate.
4. Scope one remaining authenticated view at a time after release acceptance.
   Verify authorization, caching, responsive behavior, and rollback per view;
   retain the old backend view until that view passes. Larger Drive directories
   also need a separate collector pagination change before claiming completeness.

## Non-negotiable route boundaries

- Authentik flows and OIDC callbacks
- Nextcloud DAV, sharing, login, and application routes
- XBoard application, subscription, order, and API routes
- DNS Gateway account policy and token handling
- Mirrors downloads, updater APIs, webhooks, checkout, and administrative routes

These paths are application behavior, not static presentation content, and must
never be captured by Astro fallback routing.
