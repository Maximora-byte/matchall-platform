# Remaining site migration roadmap

The first release unifies the main public site, policy pages, public service
entries, blog branding, and CV build pipeline. Stateful products remain behind
their existing reverse-proxy boundaries.

## Phase 2 — content and status

1. Migrate documentation content to Astro Starlight, preserving every existing
   documentation URL and search entry.
2. Replace only the status presentation shell with Astro components; status and
   incident data continue to come from the current API.
3. Move the Mirrors catalogue presentation to shared components without changing
   authentication, download, publishing, payment, or update API routes.

## Phase 3 — application shells

1. Apply shared tokens to DNS and Console incrementally, one authenticated view
   at a time.
2. Apply the compact dashboard variant to Investment.
3. Keep the old templates deployable until authentication, authorization,
   caching, responsive behavior, and rollback have been verified per view.

## Non-negotiable route boundaries

- Authentik flows and OIDC callbacks
- Nextcloud DAV, sharing, login, and application routes
- XBoard application, subscription, order, and API routes
- DNS Gateway account policy and token handling
- Mirrors downloads, updater APIs, webhooks, checkout, and administrative routes

These paths are application behavior, not static presentation content, and must
never be captured by Astro fallback routing.
