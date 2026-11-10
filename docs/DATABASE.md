# Database

PostgreSQL 16 holds **public announcement data only**. There are no user, session, account,
preference or tracking tables (a test enforces this).

## Layout

| Path | Purpose |
|---|---|
| `db/modelradar_db/models.py` | SQLAlchemy metadata: the reference description of the schema |
| `db/migrations/` | Alembic migrations (the source of truth for what is applied) |
| `db/tests/` | Migration, constraint and permission tests (disposable databases) |
| `docker/postgres/init/01-roles.sh` | Creates the roles on first database initialisation only |

Schema is managed by **Alembic migrations**, not by Docker init scripts. The init script only
creates the roles; every table, constraint and grant comes from a migration.

## Roles

| Role | Used by | Privileges |
|---|---|---|
| `modelradar_owner` | migrations, database container | Owns the schema; the only role that can change it |
| `modelradar_worker` | `worker` (the only writer) | SELECT, INSERT, UPDATE, DELETE on application tables; no DDL, no TRUNCATE |
| `modelradar_api` | `api` | SELECT on application tables only |

Neither application role is superuser or can create objects, and neither can read or modify
`alembic_version`. Migration `0001` applies these grants explicitly (skipping roles that do not
exist), so correctness does not depend on the init script's default privileges.

## Schema overview

```
categories ──< company_categories >── companies ──< sources ──< sync_runs
    │                                     │             │
    │                                     └──< announcements >── source_id
    │                                              │
    ├──< announcement_categories >─────────────────┤
    │                                              │
    └──< model_version_categories >── model_versions ──< announcement_models >── announcements
                                          │  (first_announcement_id -> announcements)
                                        models ── company
```

| Table | Notes |
|---|---|
| `categories` | `slug` unique, optional `parent_id` (self-reference, restrict delete) |
| `companies` | `slug` unique, `website_url` required, `country`/`description` nullable |
| `company_categories` | composite PK, cascade |
| `sources` | `kind` (rss/atom/github/api/sitemap/html/manual), `hosting` (first_party/official_third_party), `content_scope` (dedicated_ai/mixed), `verification_level` (default `http_only`), `relevance_rules` and `extractor_config` as JSONB, polling and sync state. `status` is NULL until the first sync. Unique `(company_id, url)` |
| `announcements` | Original `title` and source `description` (nullable). `original_url` unique. `published_at` nullable with `published_precision` (`day`/`datetime`); a CHECK requires both or neither. `first_seen_at` is separate and defaults to now. `kind` defaults to `other`. `metadata` JSONB nullable |
| `announcement_categories` | composite PK, cascade |
| `models` | `family_name`, unique `(company_id, slug)` |
| `model_versions` | `display_name`, nullable `version_label`, `first_announced_at` + precision (same pair rule), required `first_announcement_id` (provenance, restrict delete). Unique `(model_id, display_name)` |
| `model_version_categories` | composite PK, cascade |
| `announcement_models` | links announcements to model versions; `matched_text` records the literal text that matched |
| `sync_runs` | one row per source sync attempt; counts default to 0; removed with their source |

Enumerations are `TEXT` columns with `CHECK` constraints. Indexes: publication date
(`published_at DESC NULLS LAST`), company + date, source, kind, full-text (GIN on title and
description), trigram on model version names (`pg_trgm`), and foreign-key lookups.

Deleting a company or source that has announcements, or an announcement that is a model
version's first announcement, is refused (`RESTRICT`), so provenance cannot be lost silently.

## Migration commands

Migrations always run as the **owner** role. The `migrate` Compose service (profile `tools`)
does this and is not started by `docker compose up`.

```bash
# Apply all pending migrations (safe to repeat)
docker compose run --rm migrate

# Show the current version
docker compose run --rm migrate alembic current

# Show history
docker compose run --rm migrate alembic history

# Roll back everything (destroys all table data; development only)
docker compose run --rm migrate alembic downgrade base
```

From a host Python environment (`cd db && pip install -r requirements-dev.txt`):

```bash
# PowerShell: $env:MIGRATION_DATABASE_URL = "postgresql+psycopg://modelradar_owner:<password>@localhost:5432/modelradar"
# bash:       export MIGRATION_DATABASE_URL=...
alembic upgrade head
alembic current
```

The password is in your git-ignored `.env` (`POSTGRES_OWNER_PASSWORD`).

Creating a new migration: edit `db/modelradar_db/models.py`, then
`alembic revision --autogenerate -m "describe change"`, review and edit the generated file, and
add tests. The `test_migrations_match_models` test fails if models and migrations diverge.

## Tests

Tests create and drop their own disposable databases (`modelradar_test_<random>`); they never
touch the development database. They need a superuser connection to a Postgres server:

```bash
cd db
# PowerShell: $env:TEST_DATABASE_ADMIN_URL = "postgresql+psycopg://modelradar_owner:<password>@localhost:5432/postgres"
pytest
```

They cover: migration from an empty database, expected tables, version tracking, repeatable
up/down/up, model/migration drift, foreign keys, unique and check constraints, nullable and
precise publication dates, and per-role permissions.
