# Astro expansion report

Date: 2026-09-30

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

DNS, Console, and Investment should be migrated progressively as Astro shells or component islands while their authenticated and data-processing backends remain unchanged. Each route must keep a backend fallback until its feature-level regression suite passes.
