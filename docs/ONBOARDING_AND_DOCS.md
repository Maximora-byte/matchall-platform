# User onboarding and documentation entry

## Existing route contracts

- Console: the static landing page is optional; `/login` starts the existing OIDC
  flow, `/auth/callback` returns to `/console`, and `/console` serves the Hub
  authenticated or anonymous page. An existing session can enter `/console`
  directly. No service-provisioning endpoint is introduced.
- Account: `/register` is the existing invite-labelled entry; this change does
  not modify the identity provider's deployed enrollment flow or create invites.
- DNS: `/login` and `/guide` are declared by `services/dns/app.py`; `/account` is
  not a declared account-page route there. The static DNS landing now points to
  `/login`. Operators should verify their existing reverse-proxy mapping before
  deployment; no production route change is included.

## Documentation entry and compatibility

New Console links use `https://docs.maximoraverse.org`, matching the docs-site
Astro `site` and Hub's existing `DOCS_URL` default. Authenticated Console can use
its configured `DOCS_URL`. This is the repository's configured entry, not proof
of what the private production proxy currently serves.

Three maintained renderers exist: docs-site Starlight, blog `/docs/` pages and Hub
`/docs` pages. All existing article paths, feedback forms and rich guides remain.
The two changed/new guides (`getting-started`, `dns-guide`) carry the same body
across these renderers, with native frontmatter and feedback handling preserved.
Regression tests check parity, referenced local slugs, native DNS links and invite
wording. No existing blog guide is replaced with an empty redirect.

A cross-domain canonicalization/redirect migration is deliberately **not** included:
production routing is excluded from this repository and cannot be verified here.
Before such a migration, the owner must choose and verify the production host,
preserve every slug, query and useful fragment, confirm search/feedback handling,
and approve route deployment. Preserve current old URLs until then. DNS device
instructions remain maintained by the native `/guide` route, so this help entry
links to that source rather than duplicating live addresses or protocol settings.

## Verification and release boundary

Local tests use synthetic OIDC responses and never create accounts, solve
CAPTCHAs, buy plans, enable DNS filtering or install device profiles. Build the
changed Console, DNS, docs-site and blog applications; run Hub tests separately.
Live sign-in, enrollment, reverse-proxy behavior, paid activation and real-device
checks still need an owner-controlled staging/deployment review. New Console
snapshot-state documentation is labelled version-dependent and does not claim
that the separate Console feature has already been deployed.

There is no database migration. Owner review is required for the changed OIDC
return destination and DNS entry. Deploy app outputs/Hub code only after explicit
approval. Roll back those assets/code if necessary; no identity or business data
rollback is needed. Existing guide URLs remain valid in both versions.
