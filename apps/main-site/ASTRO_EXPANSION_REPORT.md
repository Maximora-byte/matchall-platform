# Astro expansion report

Date: 2026-09-30

Historical report: the deployment and validation statements below describe the
original work and were not reverified by the 2026-10-03 repository task. For
current implementation status and remaining acceptance, use the
[roadmap](MIGRATION_ROADMAP.md) and
[upgrade release checklist](../../docs/UPGRADE_RELEASE_READINESS.md).

## Shipped

### Documentation

- Rebuilt with Astro Starlight.
- Preserved the existing document URLs.
- Kept search, sitemap, feedback submission, and the existing documentation API.
- Supports system light/dark mode and Starlight's optional manual override.

### Status

- Rebuilt as an Astro static shell.
- Live service and incident data continues to come from the existing `/api/status` endpoint.
- RSS and API routes remain on the existing backend.
- Supports system light/dark mode.

### Mirrors catalog

- Rebuilt only the public root catalog with Astro.
- Project data continues to come from `/api/v1/projects`.
- Project, download, login, account, pricing, checkout, webhook, API, and admin routes remain on the existing FastAPI service.
- Supports system light/dark mode and client-side project filtering.

## Deployment boundary

The Caddy configuration serves only the new static presentation routes. Dynamic application routes remain reverse-proxied to their original services. No database, authentication flow, download handler, or application API was migrated.

## Validation

- Astro checks and production builds passed for all three sites.
- Public pages and static assets returned HTTP 200.
- Existing API, authentication, and project routes retained their expected status and redirects.
- Mobile light/dark browser checks passed without horizontal overflow or console errors.
- Caddy was hot reloaded; Caddy and application containers were not restarted.

## Next phase

DNS, Console, and Investment entry/public shells now exist in the repository.
Remaining authenticated views should be scoped individually while their
data-processing backends remain unchanged. Each migrated view must keep a
backend fallback until its feature-level regression suite passes. Follow the
current roadmap above for the pending reliability and documentation batch.
