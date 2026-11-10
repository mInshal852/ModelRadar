# ModelRadar

A public dashboard of AI model announcements, collected **only from official company sources**
(company blogs, release notes, official feeds, and official GitHub/Hugging Face organizations).

ModelRadar is a public-information site, not a SaaS product:

- No login, accounts, admin panel or authentication of any kind.
- No personal data collected or stored. No analytics, tracking or telemetry.
- No sample, dummy or fabricated announcements. The database starts empty and fills only from real sources.
- Every announcement links to its original official source. Titles are stored exactly as published.

> **Status: Phase 0 (foundations) complete.** The stack runs and is empty by design. Source ingestion
> starts in Phase 1. See [docs/ROADMAP.md](docs/ROADMAP.md).

## Architecture

```
Browser -> Next.js (web) -> FastAPI (api, GET only) -> PostgreSQL
                                                          ^
        config/*.yaml (in git) -> Python worker ----------+
```

| Directory | Purpose |
|---|---|
| `web/` | Next.js, TypeScript, Tailwind CSS. Public, read-only UI. |
| `api/` | FastAPI. GET endpoints only; connects with a read-only database role. |
| `worker/` | Python sync worker. The only component that writes to the database. |
| `config/` | Category taxonomy and (from Phase 1) company and source definitions. |
| `docker/` | Container support files (database role initialisation). |
| `scripts/` | Environment setup and project checks. |
| `docs/` | Architecture, privacy and roadmap documentation. |

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/PRIVACY.md](docs/PRIVACY.md).

## Run locally

Prerequisite: Docker Desktop (or Docker Engine) with Docker Compose v2.

1. Create your local environment file. It generates random database credentials and never
   overwrites an existing `.env`:

   ```bash
   # Windows (PowerShell)
   powershell -ExecutionPolicy Bypass -File scripts/init-env.ps1

   # macOS / Linux
   sh scripts/init-env.sh
   ```

2. Start everything:

   ```bash
   docker compose up --build
   ```

3. Open the services (all bound to `127.0.0.1` only):

   | Service | URL |
   |---|---|
   | Web | http://localhost:3000 |
   | API | http://localhost:8000/health (docs at `/docs`) |
   | PostgreSQL | `localhost:5432` (credentials in `.env`) |

4. Check health: `docker compose ps` should show every service as `healthy`.

Stop with `docker compose down`. Add `-v` to also delete the local database volume.

## Development checks

Run the same checks as CI:

```bash
# Config and privacy guards (needs: pip install pyyaml)
python scripts/validate_config.py
python scripts/check_privacy.py

# API and worker (needs Python 3.12)
cd api    && pip install -r requirements-dev.txt && ruff check . && ruff format --check . && mypy && pytest
cd worker && pip install -r requirements-dev.txt && ruff check . && ruff format --check . && mypy && pytest

# Web (needs Node 24 - see web/.nvmrc; Docker uses the same major version)
cd web && npm install && npm run lint && npm run typecheck && npm run format:check && npm run build
```

Commit `web/package-lock.json` after the first `npm install` so CI uses `npm ci`.

## Contributing rules

Do not add authentication, user accounts, analytics, telemetry, third-party font/CDN loading,
admin features, or sample announcement data. `scripts/check_privacy.py` enforces part of this in CI.
