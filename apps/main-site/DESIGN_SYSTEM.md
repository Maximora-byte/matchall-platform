# MatchAll public web design system

This Astro site is the reference implementation for MatchAll's public-facing
visual language. Product applications keep their own runtime and routes; only
their public entry surfaces should reuse these principles.

## Principles

- Dark, restrained surfaces with service-specific accent colors.
- Strong type hierarchy, generous whitespace, and concise copy.
- Static-first delivery for public content; APIs remain behind their existing
  application boundaries.
- Motion is decorative only and disabled by `prefers-reduced-motion`.
- Every new public page must follow `prefers-color-scheme`: dark system mode
  uses the dark palette and light system mode uses the light palette. A manual
  override may be offered, but its unset/default state must remain automatic.
- Authentication, callback, DAV, subscription, download, and API paths must
  never be shadowed by an Astro route.

## Shared tokens

- Canvas: `#07090e`
- Elevated surface: translucent slate with a low-contrast border
- Text: `#f4f7fb`; secondary text: `#9ba8bb`
- Brand accent: cyan → violet gradient
- Radius: 14px controls, 24–30px content panels
- Content width: 1180px maximum

## Product treatment

- Blog: Fuwari remains the content theme; reuse MatchAll brand assets.
- Documentation: use Astro Starlight rather than Fuwari.
- Account, Drive, Network: keep the current application backends and use the
  shared public-entry styling only.
- Dashboards and consoles: prioritize density and accessibility over decorative
  landing-page effects.

## Release contract

Every public release must pass Astro diagnostics and build in a clean output
directory, preserve a timestamped production backup, and verify the public URL,
critical links, metadata, and protected application routes after deployment.
