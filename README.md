# ModelRadar

A public dashboard of AI model announcements, collected **only from official company sources**
(company blogs, release notes, official feeds, and official GitHub/Hugging Face organizations).

ModelRadar is a public-information site, not a SaaS product:

- No login, accounts, admin panel or authentication of any kind.
- No personal data collected or stored. No analytics, tracking or telemetry.
- No sample, dummy or fabricated announcements. The database starts empty and fills only from real sources.
- Every announcement links to its original official source. Titles are stored exactly as published.

> **Status: Phases 0-2 complete; Phase 3 (frontend dashboard and read API) implemented.** The
> worker collects real announcements from ten official feeds and the web app shows them.
> See [docs/ROADMAP.md](docs/ROADMAP.md), [docs/DESIGN.md](docs/DESIGN.md),
> [docs/API.md](docs/API.md), [docs/SOURCES.md](docs/SOURCES.md) and
> [docs/INGESTION.md](docs/INGESTION.md).

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
| `db/` | Alembic migrations, SQLAlchemy schema metadata and database tests. See [docs/DATABASE.md](docs/DATABASE.md). |
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

3. Create the database schema (one-off, safe to repeat; runs as the owner role):

   ```bash
   docker compose run --rm migrate
   ```

   Then load the official company and source configuration (idempotent, never deletes, never
   creates announcements):

   ```bash
   docker compose run --rm worker python -m worker.cli sync-config
   ```

   Source configuration, verification and relevance rules are explained in
   [docs/SOURCES.md](docs/SOURCES.md).

   The worker then collects announcements automatically on each source's poll interval. To
   collect immediately and see the result:

   ```bash
   docker compose run --rm worker python -m worker.cli ingest
   docker compose run --rm worker python -m worker.cli sync-status
   ```

   Details: [docs/INGESTION.md](docs/INGESTION.md). Set `INGESTION_ENABLED=false` in `.env` to pause the recurring loop.

4. Open the services (all bound to `127.0.0.1` only):

   | Service | URL |
   |---|---|
   | Web | http://localhost:3000 |
   | API | http://localhost:8000/health (docs at `/docs`) |
   | PostgreSQL | `localhost:5432` (credentials in `.env`) |

5. Check health: `docker compose ps` should show every service as `healthy`.

Stop with `docker compose down`. Add `-v` to also delete the local database volume.

## Development checks

Run the same checks as CI:

```bash
# Config and privacy guards (needs: pip install -r worker/requirements.txt)
python scripts/validate_config.py
python scripts/check_privacy.py

# API and worker (needs Python 3.12)
cd api    && pip install -r requirements-dev.txt && ruff check . && ruff format --check . && mypy && pytest   # needs TEST_DATABASE_ADMIN_URL
cd worker && pip install -r requirements-dev.txt && ruff check . && ruff format --check . && mypy && pytest
# (worker database tests also need TEST_DATABASE_ADMIN_URL, like the db/ tests)

# Database migrations and tests (needs Python 3.12 and TEST_DATABASE_ADMIN_URL; see docs/DATABASE.md)
cd db && pip install -r requirements-dev.txt && ruff check . && ruff format --check . && mypy && pytest

# Web (needs Node 24 - see web/.nvmrc; Docker uses the same major version)
cd web && npm install && npm run lint && npm run typecheck && npm run format:check && npm test && npm run build
# Browser checks against a production build and the running stack: see docs/DESIGN.md
```

Commit `web/package-lock.json` after the first `npm install` so CI uses `npm ci`.

## Contributing rules

Do not add authentication, user accounts, analytics, telemetry, third-party font/CDN loading,
admin features, or sample announcement data. `scripts/check_privacy.py` enforces part of this in CI.
