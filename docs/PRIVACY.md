# Privacy

ModelRadar publishes public information only and collects nothing about its visitors.

| Rule | How it is enforced |
|---|---|
| No authentication, accounts, profiles or admin | No such code or tables exist; API exposes GET routes only (tested) |
| No personal data stored | Database schema contains public announcement data only |
| No analytics or tracking | No analytics dependencies; `scripts/check_privacy.py` fails CI if one appears |
| No telemetry | `NEXT_TELEMETRY_DISABLED=1` in Docker/CI; `next telemetry disable` runs before dev/build |
| Self-hosted fonts | Instrument Sans and Newsreader come from npm (`@fontsource-variable/*`); no Google Fonts or CDNs |
| No third-party requests from visitors' browsers | CSP restricts scripts, styles, images, fonts and connections to `self` |
| No cookies | The app sets none (a test enforces it). The light/dark choice is kept only in this browser's `localStorage` and never sent anywhere |
| No visitor IPs in logs | API access log disabled; Next.js does not log client IPs |
| Referrer privacy | `Referrer-Policy: no-referrer`; outbound links will also use `rel="noopener noreferrer"` |

## Secrets

Database credentials live in a git-ignored `.env` generated locally by `scripts/init-env.*`.
`.env.example` contains placeholders only. The database port is bound to `127.0.0.1`.

## Data outbound

The worker (not visitors) contacts official company sources to collect public announcements,
using an identifying User-Agent and respecting robots.txt (from Phase 1).
