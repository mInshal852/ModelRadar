# RSS/Atom ingestion

Phase 2 collects real announcements from the enabled RSS/Atom sources in `config/` and stores
them in the `announcements` table. It does **not** scrape HTML, detect models, classify, or use
any LLM. Every announcement keeps its original title and URL and links to the official source.

Code: `worker/worker/ingest/` (`dates.py`, `entries.py`, `fetcher.py`, `store.py`,
`runner.py`, `service.py`). Sources must first be loaded with `sync-config` (see
[SOURCES.md](SOURCES.md)).

## Running it

```bash
# Synchronise all enabled feeds now (manual, for development and testing)
docker compose run --rm worker python -m worker.cli ingest
docker compose run --rm worker python -m worker.cli ingest --company openai
docker compose run --rm worker python -m worker.cli ingest --url https://mistral.ai/news/rss
docker compose run --rm worker python -m worker.cli ingest --due-only   # only sources whose interval elapsed

# See each source's status and its latest run
docker compose run --rm worker python -m worker.cli sync-status
```

The `worker` service also runs the recurring loop: every `INGESTION_TICK_SECONDS` (60) it
synchronises the sources whose `poll_interval_minutes` have elapsed. Set
`INGESTION_ENABLED=false` in `.env` to pause it (the worker then only keeps its heartbeat).
Ingestion runs as the `modelradar_worker` database role, never the owner; the API role stays
read-only.

## Pipeline per source

1. **Lock.** A PostgreSQL advisory lock per source prevents overlapping runs, also across
   several worker processes. A source that is already running is skipped (no run row).
2. **Record.** A `sync_runs` row (`running`) is committed before fetching, so crashes stay
   visible. Leftover `running` rows from a crashed run are closed as failed.
3. **Fetch.** Conditional request (`If-None-Match` / `If-Modified-Since` from the stored
   `etag` / `last_modified`), robots.txt respected, per-domain minimum interval (2 s), timeout
   (20 s), up to 3 attempts with exponential backoff and jitter for network errors, 429 and
   5xx (a `Retry-After` up to 60 s is honoured; a longer one stops retrying). 401, 403, 404, 410
   and other 4xx are not retried and nothing is done to get around them.
   The User-Agent is `ModelRadar/0.1 (+https://github.com/mInshal852/ModelRadar; ...)`.
4. **Parse.** RSS and Atom via feedparser. A page that is not a feed (for example HTML served
   with status 200) is a failure.
5. **Validate and filter.** An entry needs a title and an absolute http(s) URL, otherwise it is
   skipped. Then the source's relevance rules are applied (filtered entries are not stored).
6. **Store**, in one transaction together with the run result and source status.

## What is stored

| Field | Source |
|---|---|
| `title` | the feed title, exactly (only surrounding whitespace trimmed) |
| `original_url` | the feed link, exactly as published |
| `description` | the feed's description as plain text (tags removed, entities decoded, whitespace collapsed), or `NULL` if the feed has none. Never generated |
| `published_at`, `published_precision` | the feed's date converted to UTC; `NULL` when missing or invalid |
| `content_hash` | SHA-256 of title, URL and description (detects content changes) |
| `metadata` | `{"feed_categories": [...]}` when the feed tags the entry; `description_truncated` if cut at 10 000 characters |
| `kind` | always `other` for now (classification comes later) |
| `first_seen_at` | database time of discovery. Separate from `published_at` and never used as a substitute |

### Dates

- Timezone-aware values are converted to UTC. Values with no offset are treated as UTC.
- A value that is only a date (`2026-11-06`, `Fri, 06 Nov 2026`) is stored at 00:00 UTC with
  `published_precision = 'day'`. No time of day is invented.
- A value that states a time keeps `published_precision = 'datetime'`, even when that time is
  midnight. Some real feeds publish midnight timestamps for what are effectively dates; they
  are stored as given (the first run shows none with day precision).
- Missing or invalid dates give `NULL` / `NULL`; the announcement is still stored.

## Duplicates and updates

`original_url` is unique in the database. In addition, URLs that differ only by the case of the
scheme/host or a trailing slash are recognised as the same announcement; the fragment and
query are significant (release notes distinguish entries only by `#fragment`). The stored
`original_url` is never rewritten. Within one feed a repeated URL is stored once, and a URL
already stored (by any source) is not inserted again.

When `content_hash` changes, `title`, `description`, `metadata` and `updated_at` are updated.
`published_at`, `published_precision`, `first_seen_at`, `kind`, company and source are kept. A
publication date is only filled in when the stored one is `NULL`.

## Source status and history

Existing status values are used: a success sets `ok`, clears `last_error`, resets
`consecutive_failures` and sets `last_synced_at`. A failure increments `consecutive_failures`,
sets `last_error` and the status `degraded` (1-2 failures) or `failing` (3 or more). A 304
counts as a success. Disabled sources are never synchronised. Failures never delete data.

`sync_runs` records the source, start and finish time, status (`success` / `failed`), HTTP
status, `items_found` (entries in the feed), `items_new` (inserted) and `items_filtered`
(dropped by relevance rules), and the error text. Entries skipped as invalid, updated or
unchanged are shown in the command output but are not columns in `sync_runs`.

## Scheduling

A source is due when `poll_interval_minutes` have passed since its last attempt (a source that
was never attempted is due at once). After failures the wait doubles per consecutive failure,
capped at 24 hours, so broken sources are not hammered. Sources are processed one after
another; per-domain limits apply.

## Tests

`worker/tests/` covers parsing (RSS, Atom, missing fields, dates, precision, time zones,
descriptions), relevance, the fetcher (conditional requests, retries, backoff, 304/403/404/429/5xx,
robots.txt, timeouts), and database behaviour (inserts, duplicates, repeated runs, updates, run
history, status transitions, permissions, overlapping runs). All HTTP is mocked; no test uses
the network.
