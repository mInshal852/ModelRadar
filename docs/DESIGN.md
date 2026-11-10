# Frontend design

The web app (`web/`) is a server-rendered Next.js 15.5.29 / React / TypeScript / Tailwind
interface over the read-only API. It stores nothing about visitors.

## Direction

A research instrument rather than a dashboard kit: a calm, dark-first interface where the feed is
a **dated ledger**. Announcements are grouped under their publication day in a left gutter (above
the rows on narrow screens), undated ones form a final "Date not stated" group, and rows are
separated by hairlines instead of identical shadowed cards. One memorable element (the ledger)
and otherwise quiet surfaces.

## Tokens (`web/app/globals.css`, `web/tailwind.config.ts`)

Colours are CSS variables switched by `data-theme` on `<html>`, so light and dark share classes.

| Token | Dark | Light |
|---|---|---|
| `bg` / `surface` / `raised` | `#0c1013` / `#12171b` / `#181e23` | `#f6f7f4` / `#ffffff` / `#eff1ed` |
| `line` / `line-strong` | `#232b32` / `#33404a` | `#dde1da` / `#c5cbc2` |
| `ink` / `muted` / `faint` | `#e8edf0` / `#9aa6af` / `#6f7c86` | `#12181c` / `#55626b` / `#7a868e` |
| `accent` (links, active, focus) | `#55bfd0` | `#0b7285` |
| `signal` (model releases, notices) | `#e2a948` | `#9a5b00` |
| `ok` / `warn` / `danger` | `#5cbf8c` / `#e2a948` / `#ee7a6c` | `#1f7a4f` / `#9a5b00` / `#b3382c` |

- **Type:** Instrument Sans (interface) and Newsreader (page titles and announcement titles),
  both self-hosted from npm (`@fontsource-variable/*`). Scale 12/13/15/18/22/28/36 px; tabular
  numerals throughout.
- **Shape:** 6 px controls, 10 px panels, full-round chips; hairline 1 px borders; a shadow only on
  the mobile drawer.
- **Motion:** colour transitions only, a skeleton shimmer while loading, and
  `prefers-reduced-motion` is respected. Focus is one 2 px accent outline everywhere.
- **Breakpoints:** `xs` 480, `md` 768 (sidebar appears), `lg` 1024 (sources table). Layouts
  were checked at 375, 820 and 1360 px with no horizontal overflow.

Components live in `web/components/`: shell and navigation (`shell.tsx`, `nav.tsx`), theme
switcher, filter bar, announcement row, day-grouped feed, pagination, and shared states
(`ui.tsx`: page header, monogram, badges, chips, empty/error states, skeleton).

## Behaviour and honesty rules

- Titles and descriptions are shown exactly as stored; a missing description renders nothing.
- A missing date shows "Date not stated". Date-only values show no time. A time is shown (in UTC)
  only when the source stated one that is not exactly midnight.
- `first_seen_at` is never shown or used. Sorting is by publication date only.
- Unclassified announcements are labelled "Unclassified". Categories shown on a card are the
  company's until classification exists. Counts come from real records.
- The Models page always says the directory is not exhaustive and shows an honest empty state.
- Company marks are text monograms; no logos, images or external fonts.

## Navigation: why same-page changes use full page loads

Filters, search, pagination and the in-feed category chips are plain links and a plain GET form,
so every change loads the page. This is deliberate. In production builds of Next.js 15.5.29,
client-side transitions between URLs of the same page (`/` to `/?page=2`) never completed (no
console, network or server error), while navigation between different pages worked and Next.js
15.1.6 worked. Full page loads are reliable, keep URLs shareable, make back/forward and refresh
exact, and work without JavaScript. Trade-offs: the page reloads (about 250 ms server time),
scroll resets, and search runs on Enter instead of while typing. Moving between different pages
(Models, Sources, ...) still uses client-side navigation. Revisit when a newer 15.5.x release is
available.

- The filter form has `autocomplete="off"` so browsers do not restore stale control values on
  back/forward.
- Selecting a filter, or pressing Enter in the search box, submits the form; filters that are
  already active are kept and the page resets to 1. A hidden submit button makes Enter work.

## Privacy

No cookies, analytics, third-party requests or external fonts; a strict content security policy
(`self` only). The theme (dark, light, or follow the system) is stored only in this browser's
`localStorage` and applied by a tiny inline script before first paint. A test enforces no cookies
and no requests to other hosts.

## Testing

- **Unit and component** (`npm test`, Vitest + Testing Library, 88 tests): formatting and date
  rules, URL parameter handling, API client errors, announcement rows, feed grouping,
  pagination, filter bar, theme switcher, shell/drawer navigation and states.
- **Browser** (`python web/e2e/run_e2e.py`, Playwright): 29 checks against the real running stack
  and real data, including pagination, every filter, search, back/forward, refresh, "no navigation
  hangs", strict cookies, no foreign requests, fonts, accessibility basics, theme switching, and
  mobile/tablet layouts. Run it against a **production build**:

  ```bash
  cd web && npm run build
  # copy static assets next to the standalone server, then:
  cp -r .next/static .next/standalone/.next/static
  API_INTERNAL_URL=http://localhost:8000 PORT=3100 HOSTNAME=127.0.0.1 node .next/standalone/server.js
  E2E_BASE_URL=http://127.0.0.1:3100 python web/e2e/run_e2e.py    # E2E_SCREENSHOTS=dir to save images
  ```

  It needs `pip install playwright && python -m playwright install chromium` and the Compose stack
  (`docker compose up -d`) running; it is not part of CI because it needs the full stack.
