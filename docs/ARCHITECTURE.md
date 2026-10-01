# Architecture overview

MatchAll separates presentation applications from stateful backend services.

- Public and authenticated web applications live under `apps/`.
- Hub owns shared account-facing platform behavior.
- DNS owns account/profile management and its adapter boundary.
- Mirrors owns release metadata, update APIs, and download authorization.
- DNS transports and the maintained modDNS fork provide DNS-specific runtime
  components behind the management plane.
- WordPress extensions contain only MatchAll-owned customizations.

Databases, object storage, user files, identity-provider configuration, and
production secrets are runtime concerns and are deliberately not represented as
repository content. Deployment examples must use file-based secrets or external
secret stores and placeholder hostnames.

