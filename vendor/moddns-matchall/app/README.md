# modDNS Web Application

Rich single‑page React (Vite) interface for managing the modDNS service: DNS setup guidance, blocklists & custom rules management, query logs, account & security features, and responsive mobile navigation.

## Key Features

- Authenticated multi‑profile management (create / edit / delete profiles)
- Real‑time DNS connection status header (desktop) with collapsible navigation sidebar
- Blocklists & custom rules configuration with preferences dialog
- Query logs view (filterable in future iterations)
- Guided DNS setup (`/setup`) and Settings pages
- Account preferences & security (WebAuthn / TOTP related UI hooks)
- Mobile‑first adaptive header: logo + profile dropdown + account + menu overlay
- Full‑screen mobile navigation (reuses desktop navigation structure)
- Toast feedback (sonner) and graceful logout flow
- Accessibility & cross‑device snapshots via Playwright

## Tech Stack

| Layer | Tools |
|-------|-------|
| Framework | React 18 + TypeScript + Vite |
| Routing | react-router-dom v7 |
| State | Zustand (app store), React Context (auth, nav collapse) |
| UI / Styling | Tailwind CSS v4, Radix UI primitives, custom components in `components/ui` |
| Icons | lucide-react |
| API | Axios client (`src/api`) hitting backend endpoints |
| Auth UX | WebAuthn helper libs, custom dialogs, toasts |
| Testing | Vitest (unit), Playwright (E2E, mobile snapshots, accessibility) |
| Tooling | ESLint, TypeScript ESLint, Sentry (optional) |

## Project Structure (app/src)

```
api/                // Axios client & generated / helper API logic
assets/             // Logos, images
components/         // Reusable UI (auth, dialogs, general, primitives, shadcn-style ui)
context/            // React contexts: auth, navigation collapse
hooks/              // `useScreenDetector`, `useDnsConnectionStatus`
pages/              // Route segments (setup, blocklists, custom_rules, logs, settings, account, home, header, navigation_menu)
store/              // Zustand store(s) for profiles and app state
__tests__/          // Vitest + Playwright config & specs
lib/                // Shared utilities (if any)
```

## Navigation & Layout

- Desktop: fixed collapsible sidebar (`NavigationSection`) + top header showing current page name.
- Mobile: minimalist header (logo hidden on `/home`), profile dropdown, account button, hamburger menu opening a full‑screen adapted navigation.
- Shared navigation component adapts via `isMobile` prop.

## Profiles & Dropdown

- Profiles fetched via API client, stored in Zustand.
- Active profile switch triggers toast.
- Long profile names are truncated with ellipsis in header + dropdown list.

## Blocklists Preferences

- Invoked via settings (gear) button when `showDialogTrigger` enabled.
- Dialog component: `BlocklistsPreferencesDialog`.

## Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| VITE_API_URL | Base URL for API client | http://localhost:3000 |

Local dev sets it inline in the `dev` script. For custom values create a `.env.local` with:
```
VITE_API_URL=http://your-api:3000
```

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Start Vite dev server (binds 0.0.0.0) |
| `npm run build` | Production build |
| `npm run preview` | Preview built assets |
| `npm run lint` | Lint source code |
| `npm run test` | Run Vitest in CI mode |
| `npm run test:ui` | Interactive Vitest UI |
| `npm run test:e2e` | Headless Playwright E2E (mobile strict mode) |
| `npm run test:e2e:headed` | Headed Playwright run |
| `npm run test:e2e:inspect` | Playwright UI / inspector |
| `npm run test:e2e:report` | Open last Playwright report |
| `npm run snapshots:mobile` | Update mobile snapshot baselines |
| `npm run snapshots:mobile:ci` | CI-safe mobile snapshot update |

## Testing

Playwright projects include mobile form factors (Chromium mobile + iPhone preset). Accessibility checks integrated (axe-core). Snapshot pipeline supports enforcing visual stability on mobile (`STRICT_MOBILE=1`).

## Development Flow

1. Start backend + API dependencies (see root repo docs if applicable).
2. Run the web app:
  ```bash
  npm install
  npm run dev
  ```
3. Visit printed host (default: http://localhost:5173 or next free port).
4. Log in, create/select a profile, explore navigation.

## Mobile UX Notes

- Logo hidden specifically on `/home` to reduce redundancy.
- Profile dropdown width constrained (122px) to maintain tap target alignment.
- Full‑screen nav uses same data model as desktop—no duplication.

## Error Handling & Logout

- Logout triggers backend API call + local auth context reset.
- Failures surface user‑facing toast: “Logout failed.”

## Future Improvements (Suggestions)

- Add filtering & search in logs and blocklists.
- Persist sidebar collapse state per user.
- Dark/light theme toggle integration via next-themes (base wiring present).
- Loading & skeleton states for navigation + profile switch.

## License

Internal / proprietary (adjust if license file added).

---
For architectural deep‑dives see code comments in `hooks/`, `context/`, and `pages/header/`.
