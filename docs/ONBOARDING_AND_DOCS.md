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
Six core guides (`getting-started`, `dns-guide`, `network-guide`, `drive-guide`,
`mirrors-user`, `mirrors-developer`) use the blog Markdown files under
`apps/fuwari-site/src/content/docs/` as their maintained source. The initial
reconciliation preserves the rich blog instructions and the newer Hub-only
Mirrors upload/privacy details, and corrects claims against repository code.
Service configuration and deployment-dependent features are labelled accordingly.

After editing a source, run `python scripts/sync_guides.py --write` from the
repository root. It synchronizes the body, title, summary/description and update
date into Starlight and Hub copies, retaining native metadata (including Hub
category/version) and each existing feedback form. It never creates redirects,
changes slugs, copies feedback HTML into Hub's template-based form, or writes
unmanaged articles. Sources and targets must already exist and use the current
flat plain-scalar frontmatter; unsupported YAML, malformed/ambiguous feedback,
invalid dates or symbolic-link paths fail validation before any write.

`python scripts/sync_guides.py --check` (also the default mode) reports drift
without writing. Hub regression tests run this contract, check all six guides'
body parity and local links, and render native article titles/feedback. Synthetic
sync tests cover wrapper preservation, code fences, body separators, Unicode,
idempotence and validation failures. Normal application builds consume the
checked-in copies; a deployed Hub does not require a runtime sync process or
access to blog source files. No existing guide is replaced with an empty redirect.

Other articles, including account/security, notifications and troubleshooting,
remain outside this six-guide synchronization scope. Add them only after their
content has been reconciled; do not silently choose a shorter copy as authoritative.

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

The shared-guide update changes documentation and development tooling only.
Authentication, payments, downloads, outbound notifications, service settings
and feedback handlers are unchanged. It does not establish what version is
currently deployed; Mirrors retry instructions distinguish older one-shot
delivery from versions with a persistent queue. Review the permission/download
guidance before release. Roll back the affected guide copies, docs home/index
and sync tooling together; no user or service data restoration is needed.
