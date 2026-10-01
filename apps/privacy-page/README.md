# MatchAll privacy overview

Published 2026-09-26 at https://www.maximoraverse.org/privacy/.

Source: index.html + privacy.css. Served at /srv/personal-blog/nav-site/privacy/ by the existing Caddy static host. No framework build, feed or search-index generator exists for this navigation site. Homepage footer /privacy/ entry and seo/main.sitemap.xml entry were added; original legal policy remains https://auth.maximoraverse.org/privacy.

Reference: https://www.apple.com.cn/privacy/ reviewed by fetched content and browser. Only general hierarchy, generous spacing, editorial storytelling and expandable feature explanations inspired the design. No Apple code, illustrations, trademarks or policy promises copied. Original CSS lock illustration, existing MatchAll mark, local system fonts; no JavaScript or third-party assets on the new page.

Facts: existing public policy plus reviewed dns-platform implementation/OPERATIONS.md as of 2026-09-26. DNS content explicitly scoped to gateway logs. No global zero-log/anonymity/end-to-end-encryption promise. Optional details, persistent aggregate data, independent upstream processing and operator-access limitations distinguished. All DNS control links enter /login because anonymous settings routes return401; no claim of owner-authenticated testing.

Checks: HTML IDs and anchors, canonical metadata, staged/public sitemap and homepage discoverability, HTTP200 HTML/CSS/robots/sitemap. Playwright desktop1440/tablet768/mobile390/narrow320: no overflow, details clicks and keyboard Enter passed, reduced-motion behavior passed, zero console errors, no third-party asset requests. Four unique external URLs return200 or the expected DNS OAuth302. New page itself is static and needs no cookies. Existing infrastructure may still have its own technical/security processing.

Deployment: staged entire navigation tree at /tmp/matchall-privacy-stage. Verified no deletions or unexpected changes; atomic per-file replacement of exactly privacy/index.html, privacy/privacy.css, index.html, seo/main.sitemap.xml. No server restart. Snapshot verified at /srv/personal-blog/backups/privacy-page-20260926T1030/nav-site. No tracked source baseline existed for this static tree; source here is new, unrelated existing work preserved. Files do not claim a source commit.

Rollback: copy saved index.html and seo/main.sitemap.xml back atomically, and move the added privacy directory out of the web root. Do not overwrite unrelated later site changes from the full snapshot. Future edits should stage and review again; bump the CSS query revision when changing CSS.

## Whole-service correction (2026-09-26)
User clarified that the overview must cover other MatchAll services, not focus on DNS. Replaced four DNS-heavy cards with eight service cards: Account, Drive, Network, DNS, Mirrors, Payments, Notifications and Console. Added service jump links; rewrote data accordion to identity/files/network/DNS/downloads-payments/notifications-support-public content. Main CTA now Console/account instead of DNS. Blog/docs/status public-content boundaries included.
Additional evidence: hub-platform/docs/{account-security,drive-guide,network-guide,mirrors-user,notification-delivery}.md, hub notification preferences implementation, Mirrors implementation, existing published privacy policy. No changes to underlying service settings or formal policy. Retention/deletion/E2EE claims remain appropriately scoped.
Stage and public Playwright rerun at1440/768/390/320, all eight details, keyboard, reduced motion, nine external URLs200/302, no overflow/errors/external assets. Backup of previous page: /srv/personal-blog/backups/privacy-all-services-20260926/privacy. Published only index.html/privacy.css atomically; CSS revision20260926b. To roll back this revision restore those two files from that directory.
