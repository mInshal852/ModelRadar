# Public API

Read-only JSON API served by FastAPI (`api/`). Every route is `GET`; there is no authentication,
no user data and no write endpoint (a test checks every registered route). The API connects to
PostgreSQL with the read-only `modelradar_api` role, and its sessions are additionally set
read-only with a 5 second statement timeout. Interactive docs: `http://localhost:8000/docs`.

The web app calls the API only from the server (`API_INTERNAL_URL`); browsers never contact it.

## Conventions

- **Pagination:** `page` (from 1) and `page_size` (1-100). Lists return
  `{ "items": [...], "total": N, "page": 1, "page_size": 20, "pages": M }`. A page past the end
  returns an empty `items` list.
- **Dates** are ISO 8601 in UTC. `published_at` is the *original* publication date and may be
  `null`; it is never replaced by discovery time. `published_precision` is `day` or `datetime`.
- **Errors** always have one shape:
  `{ "error": { "code": "validation_error", "message": "...", "details": [{ "field", "message" }] } }`.
  Codes: `validation_error` (422), `not_found` (404), `method_not_allowed` (405),
  `internal_error` (500, with no internal detail).
- **Validation:** slugs match `^[a-z0-9]+(-[a-z0-9]+)*$`; `q` is 1-100 characters; `kind` is one
  of `model_release`, `update`, `deprecation`, `research`, `other`.

## Endpoints

| Route | Purpose |
|---|---|
| `GET /v1/announcements` | Announcements, newest publication date first, undated last |
| `GET /v1/categories` | The category tree with announcement and company counts |
| `GET /v1/companies` | Companies with categories and counts (`q`, `category`) |
| `GET /v1/companies/{slug}` | One company |
| `GET /v1/models` | Model families and versions (`q`, `company`); incomplete by design |
| `GET /v1/sources` | Sources with verification metadata and real sync state (`company`) |
| `GET /v1/meta` | Totals and the latest sync time |
| `GET /health`, `GET /health/db` | Liveness and database readiness |

### `GET /v1/announcements`

Filters (all optional, combinable): `q` (full-text search over title and description plus a
literal partial match on the title; `%` and `_` are matched literally), `category` (a parent
category includes its children), `company`, `kind`, `published_from` and `published_to`
(inclusive dates; announcements without a date are excluded when a range is used).

Sorting is `published_at DESC NULLS LAST, id DESC`. It never uses the discovery time.

Each item contains the exact `title`, the source's `description` (or `null`), `kind`,
`published_at`, `published_precision`, `original_url`, `source_domain`, `source_name`,
`company`, `categories` and `models`. `first_seen_at` is intentionally not exposed.

**Categories:** an announcement's own categories are used when it has any; otherwise it takes
the categories of its company (the approved inheritance rule until classification exists). The
`category` filter and the category counts use the same rule.

**Models:** `models` lists only model versions linked to the announcement. Model detection is not
built yet, so it is currently empty.

### `GET /v1/sources`

Returns configuration metadata (type, hosting, verification level and notes, poll interval) and
the actual state: `status` (`null` means never synchronised), `last_synced_at`, `last_error`,
`consecutive_failures`, `announcement_count` and the latest run (`last_run`). Internal details
(ETag, extractor configuration, relevance rules) are not exposed, and errors caused by internal
processing are shown only as "Internal processing error."

## Performance

Queries use the indexes from the schema: publication date, company and date, and the full-text
GIN index. The announcement list runs one count query and one page query, then fetches
categories and models for that page in single batched queries (no per-row queries).

## Tests

`api/tests/` runs against a disposable database created from the real migrations with synthetic
rows that exist only in that database (set `TEST_DATABASE_ADMIN_URL`, see `docs/DATABASE.md`).
They cover response shape, sorting and missing dates, pagination limits, every filter, search
edge cases (wildcards, SQL-looking input), error format, that internal errors do not leak
details, and read-only behaviour at both the route and database level.
