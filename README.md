# MatchAll Platform

Private monorepo for the first-party MatchAll web applications, backend services,
WordPress extensions, deployment references, and the maintained modDNS fork.

## Layout

- `apps/` — public and authenticated Astro/static web applications.
- `services/` — MatchAll Hub, DNS, Mirrors, and DNS transport services.
- `wordpress/` — first-party WordPress plugin and MU-plugin code.
- `vendor/moddns-matchall/` — maintained modDNS fork with its upstream license.
- `infrastructure/` — sanitized deployment examples and architecture notes.
- `docs/` — repository and service documentation.

## What is intentionally absent

This repository never contains production secrets, `.env` files, databases,
user uploads, Nextcloud data, WordPress media, release artifacts, backups,
certificates, logs, or generated dependency/build directories. Production data
must be backed up through the operational backup system, not Git.

## Development

Each app or service remains independently buildable. Read its local README and
package metadata first. Common checks are orchestrated by GitHub Actions:

```bash
# Astro applications
cd apps/main-site
npm ci
npm run check
npm run build

# Python service example
cd services/mirrors
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
for test in test_*.py; do python -m unittest -v "$test"; done
```

## Change policy

All changes go through pull requests. CI must pass before merge. Merging does
not deploy production; deployment requires a separate owner-approved process.
See `AGENTS.md` for coding-agent rules.

## Licensing

The MatchAll first-party portions are private and all rights are reserved.
Third-party components retain their own license files and attribution. Do not
remove or replace those notices.

