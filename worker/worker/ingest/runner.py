"""Per-source synchronisation: lock, fetch, parse, store, record history, update status.

Safety properties:
- A session-level PostgreSQL advisory lock per source prevents overlapping runs, even across
  several worker processes. A source that is already being synchronised is skipped.
- The run is recorded in sync_runs BEFORE fetching (committed), so a crash leaves a visible
  'running' row; such abandoned rows are closed as failed by the next run.
- Announcements, the run result and the source status are written in ONE transaction.
- Failures never delete anything.
"""

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from worker.ingest.entries import parse_feed
from worker.ingest.fetcher import FeedFetcher, FetchOutcome
from worker.ingest.store import StoreResult, store_entries
from worker.sources.schema import RelevanceRules

LOCK_NAMESPACE = 0x4D52  # 'MR'
DEGRADED_AFTER = 1
FAILING_AFTER = 3
MAX_ERROR_CHARS = 500
MAX_BACKOFF = dt.timedelta(hours=24)


@dataclass
class SourceRow:
    id: int
    company_id: int
    company_slug: str
    name: str
    kind: str
    url: str
    poll_interval_minutes: int
    etag: str | None
    last_modified: str | None
    status: str | None
    consecutive_failures: int
    relevance_rules_raw: Any
    last_run_started: dt.datetime | None

    def relevance_rules(self) -> RelevanceRules | None:
        raw = self.relevance_rules_raw
        if raw is None:
            return None
        data = json.loads(raw) if isinstance(raw, str) else raw
        return RelevanceRules.model_validate(data)


@dataclass
class IngestReport:
    url: str
    company: str
    outcome: str  # success | not_modified | failed | skipped_locked
    http_status: int | None = None
    found: int = 0
    invalid: int = 0
    filtered: int = 0
    duplicates_in_feed: int = 0
    store: StoreResult = field(default_factory=StoreResult)
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


# --- selection and scheduling ----------------------------------------------------------------


async def load_sources(
    engine: AsyncEngine, *, company: str | None = None, url: str | None = None
) -> list[SourceRow]:
    """Enabled RSS/Atom sources (status is not 'disabled'), optionally filtered."""
    query = (
        "SELECT s.id, s.company_id, c.slug AS company_slug, s.name, s.kind, s.url, "
        "s.poll_interval_minutes, s.etag, s.last_modified, s.status, s.consecutive_failures, "
        "s.relevance_rules, (SELECT max(r.started_at) FROM sync_runs r WHERE r.source_id = s.id) "
        "AS last_run_started FROM sources s JOIN companies c ON c.id = s.company_id "
        "WHERE s.kind IN ('rss', 'atom') AND s.status IS DISTINCT FROM 'disabled' "
        "AND (CAST(:company AS text) IS NULL OR c.slug = :company) "
        "AND (CAST(:url AS text) IS NULL OR s.url = :url) ORDER BY s.id"
    )
    async with engine.connect() as conn:
        rows = (await conn.execute(text(query), {"company": company, "url": url})).mappings().all()
    return [
        SourceRow(
            id=r["id"],
            company_id=r["company_id"],
            company_slug=r["company_slug"],
            name=r["name"],
            kind=r["kind"],
            url=r["url"],
            poll_interval_minutes=r["poll_interval_minutes"],
            etag=r["etag"],
            last_modified=r["last_modified"],
            status=r["status"],
            consecutive_failures=r["consecutive_failures"],
            relevance_rules_raw=r["relevance_rules"],
            last_run_started=r["last_run_started"],
        )
        for r in rows
    ]


def is_due(source: SourceRow, now: dt.datetime) -> bool:
    """Due when poll_interval_minutes have passed since the last attempt.

    After failures the wait grows exponentially (capped at 24h) so a broken source is not
    hammered. A source that has never been attempted is due immediately.
    """
    if source.last_run_started is None:
        return True
    interval = dt.timedelta(minutes=source.poll_interval_minutes)
    if source.consecutive_failures > 0:
        interval = min(interval * (2 ** min(source.consecutive_failures, 8)), MAX_BACKOFF)
        interval = max(interval, dt.timedelta(minutes=source.poll_interval_minutes))
    return now >= source.last_run_started + interval


# --- one source ------------------------------------------------------------------------------


async def _try_lock(conn: AsyncConnection, source_id: int) -> bool:
    row = await conn.execute(
        text("SELECT pg_try_advisory_lock(:ns, :id)"), {"ns": LOCK_NAMESPACE, "id": source_id}
    )
    return bool(row.scalar_one())


async def _unlock(conn: AsyncConnection, source_id: int) -> None:
    await conn.execute(
        text("SELECT pg_advisory_unlock(:ns, :id)"), {"ns": LOCK_NAMESPACE, "id": source_id}
    )


async def _start_run(engine: AsyncEngine, source_id: int) -> int:
    async with engine.begin() as conn:
        # We hold the source lock, so any 'running' row is left over from a crashed run.
        await conn.execute(
            text(
                "UPDATE sync_runs SET status = 'failed', finished_at = now(), "
                "error = 'abandoned: worker stopped before finishing' "
                "WHERE source_id = :s AND status = 'running'"
            ),
            {"s": source_id},
        )
        row = await conn.execute(
            text("INSERT INTO sync_runs (source_id, status) VALUES (:s, 'running') RETURNING id"),
            {"s": source_id},
        )
        return int(row.scalar_one())


async def _finish_success(
    conn: AsyncConnection,
    run_id: int,
    source: SourceRow,
    outcome: FetchOutcome,
    found: int,
    new: int,
    filtered: int,
) -> None:
    await conn.execute(
        text(
            "UPDATE sync_runs SET status = 'success', finished_at = now(), http_status = :http, "
            "items_found = :found, items_new = :new, items_filtered = :filtered WHERE id = :id"
        ),
        {"id": run_id, "http": outcome.status, "found": found, "new": new, "filtered": filtered},
    )
    await conn.execute(
        text(
            "UPDATE sources SET etag = :etag, last_modified = :lm, last_synced_at = now(), "
            "status = 'ok', last_error = NULL, consecutive_failures = 0 "
            "WHERE id = :id AND status IS DISTINCT FROM 'disabled'"
        ),
        {"id": source.id, "etag": outcome.etag, "lm": outcome.last_modified},
    )


async def _finish_failure(
    engine: AsyncEngine, run_id: int, source: SourceRow, http_status: int | None, error: str
) -> None:
    message = error[:MAX_ERROR_CHARS]
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE sync_runs SET status = 'failed', finished_at = now(), "
                "http_status = :http, error = :err WHERE id = :id"
            ),
            {"id": run_id, "http": http_status, "err": message},
        )
        await conn.execute(
            text(
                "UPDATE sources SET consecutive_failures = consecutive_failures + 1, "
                "last_error = :err, status = CASE WHEN consecutive_failures + 1 >= :failing "
                "THEN 'failing' ELSE 'degraded' END "
                "WHERE id = :id AND status IS DISTINCT FROM 'disabled'"
            ),
            {"id": source.id, "err": message, "failing": FAILING_AFTER},
        )


async def ingest_source(
    engine: AsyncEngine, fetcher: FeedFetcher, source: SourceRow
) -> IngestReport:
    report = IngestReport(url=source.url, company=source.company_slug, outcome="failed")

    async with engine.connect() as lock_conn:
        lock_conn = await lock_conn.execution_options(isolation_level="AUTOCOMMIT")
        if not await _try_lock(lock_conn, source.id):
            report.outcome = "skipped_locked"
            report.error = "another worker is already synchronising this source"
            return report
        try:
            return await _ingest_locked(engine, fetcher, source, report)
        finally:
            await _unlock(lock_conn, source.id)


async def _ingest_locked(
    engine: AsyncEngine, fetcher: FeedFetcher, source: SourceRow, report: IngestReport
) -> IngestReport:
    run_id = await _start_run(engine, source.id)

    async def fail(http_status: int | None, error: str) -> IngestReport:
        await _finish_failure(engine, run_id, source, http_status, error)
        report.outcome, report.http_status, report.error = "failed", http_status, error
        return report

    try:
        rules = source.relevance_rules()
    except Exception as exc:
        return await fail(None, f"invalid relevance rules in database: {type(exc).__name__}")

    try:
        outcome = await fetcher.fetch(source.url, source.etag, source.last_modified)
    except Exception as exc:  # defensive: the fetcher should not raise
        return await fail(None, f"fetch failed: {type(exc).__name__}")
    report.http_status = outcome.status

    if outcome.kind == "error":
        return await fail(outcome.status, outcome.error or "fetch failed")

    try:
        async with engine.begin() as conn:
            if outcome.kind == "not_modified":
                report.outcome = "not_modified"
                await _finish_success(conn, run_id, source, outcome, 0, 0, 0)
                return report

            parsed = parse_feed(outcome.content, rules)
            if not parsed.recognised:
                raise _FeedRejected(parsed.problems[0])
            stored = await store_entries(conn, source.company_id, source.id, parsed.entries)
            await _finish_success(
                conn, run_id, source, outcome, parsed.found, stored.inserted, parsed.filtered
            )
            report.outcome = "success"
            report.found, report.invalid, report.filtered = (
                parsed.found,
                parsed.invalid,
                parsed.filtered,
            )
            report.duplicates_in_feed = parsed.duplicates_in_feed
            report.store = stored
            report.warnings = parsed.problems
            return report
    except _FeedRejected as exc:
        return await fail(outcome.status, str(exc))
    except Exception as exc:  # transaction rolled back; record the failure honestly
        return await fail(outcome.status, f"processing failed: {type(exc).__name__}: {exc}")


class _FeedRejected(Exception):
    pass


# --- many sources ----------------------------------------------------------------------------


async def run_sources(
    engine: AsyncEngine,
    fetcher: FeedFetcher,
    *,
    only_due: bool,
    now: dt.datetime | None = None,
    company: str | None = None,
    url: str | None = None,
) -> list[IngestReport]:
    """Synchronise sources one after another (per-domain limits apply inside the fetcher)."""
    now = now or dt.datetime.now(dt.UTC)
    sources = await load_sources(engine, company=company, url=url)
    if only_due:
        sources = [s for s in sources if is_due(s, now)]
    reports: list[IngestReport] = []
    for source in sources:
        reports.append(await ingest_source(engine, fetcher, source))
    return reports
