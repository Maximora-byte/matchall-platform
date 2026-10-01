# Maximora CV

Source for [cv.maximoraverse.org](https://cv.maximoraverse.org), the bilingual portfolio and résumé site of CHANGAO MA.

## Features

- Simplified Chinese, Traditional Chinese, Japanese, English, and French pages
- Search-indexable locale routes with canonical and hreflang metadata
- Dark / light themes
- Filterable public work
- Keyboard command palette (Ctrl/Command K)
- Responsive modal navigation
- Print / save-as-PDF layout
- JSON-LD, Open Graph, sitemap, robots, and web manifest metadata
- Reduced-motion and no-JavaScript fallbacks

## Development

Requires Node.js 22.12 or newer.

    npm ci --include=dev
    npm run check
    npm run build
    npm run preview

The build script runs Astro diagnostics before producing the static dist output.

## Content

Public profile and project data lives in [src/config.ts](src/config.ts). The main presentation and interaction logic lives in [src/pages/index.astro](src/pages/index.astro), with the visual system in [src/styles/global.css](src/styles/global.css).

Do not add private contact details, credentials, internal hostnames, or unpublished work to the public configuration.

## Attribution

This site began with the MIT-licensed [DevPortfolio](https://github.com/RyanFitzgerald/devportfolio) Astro foundation by Ryan Fitzgerald. The information architecture, interface, visual system, content model, and interactions have been rebuilt for this deployment. See [LICENSE.md](LICENSE.md).
