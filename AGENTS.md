# AGENTS.md — MatchAll repository rules

## Scope

This is a private monorepo. Make the smallest change that satisfies the task.
Prefer one focused pull request over unrelated cross-service rewrites.

## Safety

- Never add or request production passwords, tokens, private keys, certificates,
  databases, user files, backups, logs, or release artifacts.
- Never connect to or mutate production infrastructure from repository tasks.
- Never deploy automatically. A merged pull request is not deployment approval.
- Use `.env.example` and synthetic fixtures only.
- Preserve third-party licenses and attribution, especially under `vendor/` and
  inherited application directories.

## Structure

- `apps/`: frontend/static applications.
- `services/`: first-party backend services.
- `wordpress/`: first-party WordPress extensions.
- `vendor/`: maintained third-party forks; avoid broad formatting churn.
- `infrastructure/`: examples only, with placeholders instead of credentials.

## Verification

- For an npm app: run `npm ci`, `npm run check` when present, and `npm run build`.
- For a Python service: install `requirements.txt`, then run every `test_*.py`
  in a separate Python process to avoid shared module/database state.
- For Go changes: run `go test ./...` in the affected module.
- For WordPress PHP changes: run `php -l` on every changed PHP file.
- State exactly which checks ran and which could not run in the PR description.

## Pull requests

- Do not push directly to `main`.
- Include purpose, affected services, test evidence, migration impact, security
  considerations, and rollback notes.
- Changes to authentication, payments, DNS routing, downloads, privacy, or data
  retention require explicit owner review.

