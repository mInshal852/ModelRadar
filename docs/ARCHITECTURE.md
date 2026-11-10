# Architecture

Approved architecture for ModelRadar. Phase 0 implements only the foundations marked below.

## Components

```
Browser -> Next.js (public, read-only) -> FastAPI (GET only) -> PostgreSQL
                                                                   ^
              config/*.yaml (in git) -> Sync worker (Python) ------+
```

- **web** (Next.js + TypeScript + Tailwind): server-rendered public pages. No forms, logins or
  client-side persistence. Fonts are self-hosted from npm packages; CSP allows `self` only.
- **api** (FastAPI): GET endpoints only (a test enforces this). Connects as `modelradar_api`,
  a read-only database role. Access logging is disabled so IP addresses are not written to logs.
- **worker** (Python): scheduler loop; the only writer. Connects as `modelradar_worker`.
  Phase 0 has a database connectivity check and heartbeat only.
- **PostgreSQL 16**: roles `modelradar_owner` (schema owner / future migrations),
  `modelradar_worker` (read/write), `modelradar_api` (read-only). Default privileges are set so
  future tables get the right grants automatically.
- **config/**: version-controlled YAML. No admin UI; changes are pull requests.

## Content rules (apply from Phase 1)

- Titles stored exactly as published; descriptions are the source's own text or excerpt, or `NULL`.
- Rule-based classification only. No LLM-generated content initially.
- `published_at` is the original publication date and is never replaced by discovery time;
  `first_seen_at` is stored separately. "New" is based on `published_at` only.
- Source verification levels: `http_only`, `content_sampled`, `content_verified`. Third-party-hosted
  publications are flagged separately.

## Database (Phase 1A)

The schema and Alembic migrations are implemented; see [DATABASE.md](DATABASE.md). Migrations
run with the owner role through the on-demand `migrate` Compose service. No data is loaded:
tables start empty.

## Official sources (Phase 1B)

Companies and sources are YAML in `config/`, validated and loaded into the database by the
worker (`python -m worker.cli sync-config`); see [SOURCES.md](SOURCES.md). The worker can also
inspect feeds (`verify-sources`) but does not yet store announcements.

## Ingestion (Phase 2)

The worker fetches enabled RSS/Atom sources on their poll intervals and stores announcements
and run history; see [INGESTION.md](INGESTION.md). It runs as the write-capable worker role.
The API stays read-only.

## Frontend and read API (Phase 3)

The API exposes GET-only endpoints ([API.md](API.md)); the Next.js app renders them on the server
([DESIGN.md](DESIGN.md)). Browsers never call the API directly.

## Phase 0 scope

Included: monorepo, Docker Compose (db, api, worker, web), environment and credential handling,
privacy defaults, CI, linting, docs, the 17-category taxonomy file.

Not included (later phases): classification, models detection, HTML extraction.
