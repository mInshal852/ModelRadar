"""End-to-end ingestion against a disposable database (mocked HTTP, real migrations).

Everything runs as the modelradar_worker role. Feeds are controlled test fixtures.
"""

import asyncio
import datetime as dt
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.feeds import ScriptedServer, atom, atom_entry, ok, rss, rss_item
from tests.test_config_validation import company, source
from worker.ingest.runner import (
    SourceRow,
    ingest_source,
    is_due,
    load_sources,
    run_sources,
)
from worker.sources.loader import LoadedConfig, validate_config_dir
from worker.sources.sync import sync_config

Builder = Callable[..., Path]
URL = "https://acme.test/feed.xml"


async def setup_sources(
    engine: AsyncEngine, make_config: Builder, **companies: dict[str, Any]
) -> list[SourceRow]:
    files = {f"{n}.yaml": yaml.safe_dump(d) for n, d in (companies or {"acme": company()}).items()}
    config, errors = validate_config_dir(make_config(companies=files), expected_top_level=None)
    assert isinstance(config, LoadedConfig), errors
    async with engine.begin() as conn:
        await sync_config(conn, config)
    return await load_sources(engine)


async def one(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).one()


async def rows(engine: AsyncEngine, sql: str, **params: Any) -> list[Any]:
    async with engine.connect() as conn:
        return list((await conn.execute(text(sql), params)).all())


# --- storing announcements -----------------------------------------------------------------


async def test_new_announcements_are_inserted(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    feed = rss(
        rss_item(title="First", link="https://acme.test/p/1", cats=("Product",)),
        rss_item(title="Second", link="https://acme.test/p/2", date="2026-11-03", desc=None),
    )
    server = ScriptedServer(ok(feed))
    report = await ingest_source(worker_engine, server.fetcher(), src)

    assert report.outcome == "success"
    assert (report.found, report.store.inserted, report.filtered, report.invalid) == (2, 2, 0, 0)
    stored = await rows(
        worker_engine,
        "SELECT title, original_url, description, published_at, published_precision, kind, "
        "metadata, first_seen_at FROM announcements ORDER BY original_url",
    )
    first, second = stored
    assert (first.title, first.original_url, first.kind) == (
        "First",
        "https://acme.test/p/1",
        "other",
    )
    assert first.published_at == dt.datetime(2026, 11, 2, 10, 0, tzinfo=dt.UTC)
    assert first.published_precision == "datetime"
    assert second.description is None
    assert (second.published_at, second.published_precision) == (
        dt.datetime(2026, 11, 3, tzinfo=dt.UTC),
        "day",
    )
    assert first.first_seen_at is not None


async def test_missing_dates_are_null_and_never_replaced_by_discovery_time(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    feed = rss(rss_item(title="Undated", link="https://acme.test/u", date=None))
    await ingest_source(worker_engine, ScriptedServer(ok(feed)).fetcher(), src)
    row = await one(
        worker_engine,
        "SELECT published_at, published_precision, first_seen_at FROM announcements",
    )
    assert row.published_at is None and row.published_precision is None
    assert row.first_seen_at is not None


async def test_entries_missing_title_or_url_are_skipped_not_stored(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    feed = rss(
        rss_item(title=None), rss_item(link=None), rss_item(title="Ok", link="https://acme.test/ok")
    )
    report = await ingest_source(worker_engine, ScriptedServer(ok(feed)).fetcher(), src)
    assert (report.found, report.invalid, report.store.inserted) == (3, 2, 1)
    assert (await one(worker_engine, "SELECT count(*) FROM announcements"))[0] == 1


async def test_atom_feed_is_ingested(worker_engine: AsyncEngine, make_config: Builder) -> None:
    atom_source = source(slug="acme-atom", kind="atom", url="https://acme.test/atom.xml")
    [src] = await setup_sources(worker_engine, make_config, acme=company(sources=[atom_source]))
    report = await ingest_source(
        worker_engine, ScriptedServer(ok(atom(atom_entry()))).fetcher(), src
    )
    assert report.outcome == "success" and report.store.inserted == 1


async def test_relevance_rules_filter_before_saving(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    rules_source = source(relevance_rules={"include_categories": ["Product"]})
    [src] = await setup_sources(worker_engine, make_config, acme=company(sources=[rules_source]))
    feed = rss(
        rss_item(title="Keep", link="https://acme.test/k", cats=("Product",)),
        rss_item(title="Drop", link="https://acme.test/d", cats=("Story",)),
    )
    report = await ingest_source(worker_engine, ScriptedServer(ok(feed)).fetcher(), src)
    assert (report.found, report.filtered, report.store.inserted) == (2, 1, 1)
    run = await one(worker_engine, "SELECT items_found, items_new, items_filtered FROM sync_runs")
    assert tuple(run) == (2, 1, 1)
    titles = [r.title for r in await rows(worker_engine, "SELECT title FROM announcements")]
    assert titles == ["Keep"]


# --- duplicates and repeated sync ----------------------------------------------------------


async def test_repeated_sync_creates_no_duplicates(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    feed = rss(rss_item(link="https://acme.test/p/1"), rss_item(link="https://acme.test/p/2"))
    server = ScriptedServer(ok(feed))
    for _ in range(3):
        report = await ingest_source(worker_engine, server.fetcher(), src)
    assert report.store.inserted == 0 and report.store.unchanged == 2
    assert (await one(worker_engine, "SELECT count(*) FROM announcements"))[0] == 2
    assert (await one(worker_engine, "SELECT count(*) FROM sync_runs"))[0] == 3


async def test_url_written_differently_is_the_same_announcement_and_stored_url_is_kept(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    await ingest_source(
        worker_engine,
        ScriptedServer(ok(rss(rss_item(link="https://acme.test/Post/")))).fetcher(),
        src,
    )
    varied = rss(rss_item(link="HTTPS://ACME.test/Post"))
    report = await ingest_source(worker_engine, ScriptedServer(ok(varied)).fetcher(), src)
    assert report.store.inserted == 0
    urls = [
        r.original_url for r in await rows(worker_engine, "SELECT original_url FROM announcements")
    ]
    assert urls == ["https://acme.test/Post/"]  # first-seen spelling is never rewritten


async def test_original_url_is_unique_across_sources(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    second = source(slug="acme-two", url="https://acme.test/feed2.xml")
    srcs = await setup_sources(worker_engine, make_config, acme=company(sources=[source(), second]))
    shared = rss(rss_item(link="https://acme.test/shared"))
    first_report = await ingest_source(worker_engine, ScriptedServer(ok(shared)).fetcher(), srcs[0])
    second_report = await ingest_source(
        worker_engine, ScriptedServer(ok(shared)).fetcher(), srcs[1]
    )
    assert first_report.store.inserted == 1
    assert second_report.store.inserted == 0
    assert (await one(worker_engine, "SELECT count(*) FROM announcements"))[0] == 1


async def test_duplicate_urls_inside_one_feed_are_stored_once(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    feed = rss(rss_item(link="https://acme.test/d"), rss_item(link="https://acme.test/d"))
    report = await ingest_source(worker_engine, ScriptedServer(ok(feed)).fetcher(), src)
    assert report.store.inserted == 1 and report.duplicates_in_feed == 1


async def test_changed_content_updates_text_but_preserves_dates(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    link = "https://acme.test/changing"
    await ingest_source(
        worker_engine,
        ScriptedServer(ok(rss(rss_item(title="Old title", link=link, desc="old")))).fetcher(),
        src,
    )
    before = await one(
        worker_engine,
        "SELECT published_at, first_seen_at, updated_at, content_hash FROM announcements",
    )
    # the feed now shows a different title/description AND a different date
    changed = rss(
        rss_item(title="New title", link=link, desc="new", date="Fri, 06 Nov 2026 09:00:00 GMT")
    )
    report = await ingest_source(worker_engine, ScriptedServer(ok(changed)).fetcher(), src)
    after = await one(
        worker_engine,
        "SELECT title, description, published_at, first_seen_at, updated_at, content_hash "
        "FROM announcements",
    )
    assert report.store.updated == 1 and report.store.inserted == 0
    assert (after.title, after.description) == ("New title", "new")
    assert after.published_at == before.published_at  # original publication date preserved
    assert after.first_seen_at == before.first_seen_at
    assert after.updated_at >= before.updated_at
    assert after.content_hash != before.content_hash
    assert (await one(worker_engine, "SELECT count(*) FROM announcements"))[0] == 1


async def test_unknown_date_is_filled_when_the_feed_later_provides_it(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    link = "https://acme.test/late-date"
    await ingest_source(
        worker_engine, ScriptedServer(ok(rss(rss_item(link=link, date=None)))).fetcher(), src
    )
    await ingest_source(
        worker_engine,
        ScriptedServer(
            ok(rss(rss_item(link=link, date="Mon, 02 Nov 2026 10:00:00 GMT")))
        ).fetcher(),
        src,
    )
    row = await one(worker_engine, "SELECT published_at, published_precision FROM announcements")
    assert row.published_at == dt.datetime(2026, 11, 2, 10, 0, tzinfo=dt.UTC)
    assert row.published_precision == "datetime"


# --- conditional requests and status ---------------------------------------------------------


async def test_etag_is_stored_and_a_304_changes_nothing(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    feed = rss(rss_item())
    first = ScriptedServer(
        ok(feed, etag='"v1"', **{"last-modified": "Mon, 02 Nov 2026 10:00:00 GMT"})
    )
    await ingest_source(worker_engine, first.fetcher(), src)

    [src] = await load_sources(worker_engine)
    assert (src.etag, src.last_modified) == ('"v1"', "Mon, 02 Nov 2026 10:00:00 GMT")

    second = ScriptedServer(httpx.Response(304))
    report = await ingest_source(worker_engine, second.fetcher(), src)
    assert report.outcome == "not_modified"
    assert second.feed_requests()[0].headers["if-none-match"] == '"v1"'
    state = await one(
        worker_engine, "SELECT status, etag, consecutive_failures, last_synced_at FROM sources"
    )
    assert (state.status, state.etag, state.consecutive_failures) == ("ok", '"v1"', 0)
    assert (await one(worker_engine, "SELECT count(*) FROM announcements"))[0] == 1
    last_run = await one(
        worker_engine,
        "SELECT status, http_status, items_found FROM sync_runs ORDER BY id DESC LIMIT 1",
    )
    assert tuple(last_run) == ("success", 304, 0)


async def test_success_sets_status_ok_and_clears_errors(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    await ingest_source(
        worker_engine, ScriptedServer(httpx.Response(500)).fetcher(max_attempts=1), src
    )
    await ingest_source(worker_engine, ScriptedServer(ok(rss(rss_item()))).fetcher(), src)
    state = await one(
        worker_engine,
        "SELECT status, last_error, consecutive_failures, last_synced_at FROM sources",
    )
    assert (state.status, state.last_error, state.consecutive_failures) == ("ok", None, 0)
    assert state.last_synced_at is not None


@pytest.mark.parametrize("status", [403, 404, 410, 429, 500, 503])
async def test_http_failures_are_recorded(
    worker_engine: AsyncEngine, make_config: Builder, status: int
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    server = ScriptedServer(httpx.Response(status))
    report = await ingest_source(worker_engine, server.fetcher(max_attempts=2), src)
    assert report.outcome == "failed" and report.http_status == status
    run = await one(
        worker_engine, "SELECT status, http_status, error, finished_at, items_found FROM sync_runs"
    )
    assert (run.status, run.http_status, run.items_found) == ("failed", status, 0)
    assert str(status) in run.error and run.finished_at is not None
    state = await one(
        worker_engine,
        "SELECT status, consecutive_failures, last_error, last_synced_at FROM sources",
    )
    assert (state.status, state.consecutive_failures) == ("degraded", 1)
    assert str(status) in state.last_error and state.last_synced_at is None


async def test_failure_count_escalates_to_failing_and_recovers(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    statuses = []
    for _ in range(3):
        await ingest_source(worker_engine, ScriptedServer(httpx.Response(404)).fetcher(), src)
        state = await one(worker_engine, "SELECT status, consecutive_failures FROM sources")
        statuses.append(tuple(state))
    assert statuses == [("degraded", 1), ("degraded", 2), ("failing", 3)]
    await ingest_source(worker_engine, ScriptedServer(ok(rss(rss_item()))).fetcher(), src)
    state = await one(worker_engine, "SELECT status, consecutive_failures FROM sources")
    assert tuple(state) == ("ok", 0)


async def test_failures_never_delete_collected_announcements(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    await ingest_source(worker_engine, ScriptedServer(ok(rss(rss_item()))).fetcher(), src)
    await ingest_source(worker_engine, ScriptedServer(httpx.Response(403)).fetcher(), src)
    await ingest_source(worker_engine, ScriptedServer(ok(rss())).fetcher(), src)  # empty feed
    assert (await one(worker_engine, "SELECT count(*) FROM announcements"))[0] == 1


async def test_html_instead_of_a_feed_is_a_failure(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    server = ScriptedServer(ok(b"<html><body>Please enable JavaScript</body></html>"))
    report = await ingest_source(worker_engine, server.fetcher(), src)
    assert report.outcome == "failed" and "not a recognisable" in (report.error or "")
    assert (await one(worker_engine, "SELECT count(*) FROM announcements"))[0] == 0


async def test_robots_block_is_recorded_as_a_failure_without_fetching(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    server = ScriptedServer(ok(rss(rss_item())), robots="User-agent: *\nDisallow: /\n")
    report = await ingest_source(worker_engine, server.fetcher(), src)
    assert report.outcome == "failed" and "robots.txt" in (report.error or "")
    assert server.feed_requests() == []


async def test_processing_error_rolls_back_and_is_recorded(
    worker_engine: AsyncEngine, make_config: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    [src] = await setup_sources(worker_engine, make_config)

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr("worker.ingest.runner.store_entries", boom)
    report = await ingest_source(worker_engine, ScriptedServer(ok(rss(rss_item()))).fetcher(), src)
    assert report.outcome == "failed" and "RuntimeError" in (report.error or "")
    assert (await one(worker_engine, "SELECT count(*) FROM announcements"))[0] == 0
    run = await one(worker_engine, "SELECT status, finished_at FROM sync_runs")
    assert run.status == "failed" and run.finished_at is not None


# --- history, selection and scheduling ---------------------------------------------------------


async def test_successful_run_history(worker_engine: AsyncEngine, make_config: Builder) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    await ingest_source(worker_engine, ScriptedServer(ok(rss(rss_item()))).fetcher(), src)
    run = await one(
        worker_engine,
        "SELECT source_id, status, http_status, items_found, items_new, items_filtered, "
        "started_at, finished_at, error FROM sync_runs",
    )
    assert run.source_id == src.id and run.status == "success" and run.http_status == 200
    assert (run.items_found, run.items_new, run.items_filtered, run.error) == (1, 1, 0, None)
    assert run.finished_at >= run.started_at


async def test_abandoned_running_rows_are_closed_by_the_next_run(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    async with worker_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO sync_runs (source_id, status) VALUES (:s, 'running')"), {"s": src.id}
        )
    await ingest_source(worker_engine, ScriptedServer(ok(rss(rss_item()))).fetcher(), src)
    statuses = [
        r.status for r in await rows(worker_engine, "SELECT status FROM sync_runs ORDER BY id")
    ]
    assert statuses == ["failed", "success"]
    abandoned = await one(worker_engine, "SELECT error FROM sync_runs ORDER BY id LIMIT 1")
    assert "abandoned" in abandoned.error


async def test_disabled_sources_are_never_synchronised(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    off = source(enabled=False, disabled_reason="Not an announcement feed.")
    await setup_sources(worker_engine, make_config, acme=company(sources=[off]))
    assert await load_sources(worker_engine) == []
    server = ScriptedServer(ok(rss(rss_item())))
    assert await run_sources(worker_engine, server.fetcher(), only_due=False) == []
    assert server.requests == []


async def test_non_feed_kinds_are_not_ingested(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    html = source(
        slug="acme-html",
        kind="html",
        url="https://acme.test/news",
        enabled=False,
        disabled_reason="HTML extraction is not implemented.",
    )
    await setup_sources(worker_engine, make_config, acme=company(sources=[html]))
    assert await load_sources(worker_engine) == []


def _src(**kw: Any) -> SourceRow:
    base: dict[str, Any] = {
        "id": 1,
        "company_id": 1,
        "company_slug": "acme",
        "name": "n",
        "kind": "rss",
        "url": URL,
        "poll_interval_minutes": 60,
        "etag": None,
        "last_modified": None,
        "status": "ok",
        "consecutive_failures": 0,
        "relevance_rules_raw": None,
        "last_run_started": None,
    }
    return SourceRow(**{**base, **kw})


def test_due_logic_uses_the_configured_interval() -> None:
    now = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.UTC)
    assert is_due(_src(last_run_started=None), now)
    assert not is_due(_src(last_run_started=now - dt.timedelta(minutes=59)), now)
    assert is_due(_src(last_run_started=now - dt.timedelta(minutes=60)), now)


def test_failing_sources_back_off_exponentially_with_a_cap() -> None:
    now = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.UTC)
    one_fail = _src(consecutive_failures=1, last_run_started=now - dt.timedelta(minutes=100))
    assert not is_due(one_fail, now)  # needs 120 min after one failure
    assert is_due(
        _src(consecutive_failures=1, last_run_started=now - dt.timedelta(minutes=121)), now
    )
    many = _src(consecutive_failures=20, last_run_started=now - dt.timedelta(hours=23))
    assert not is_due(many, now)
    assert is_due(_src(consecutive_failures=20, last_run_started=now - dt.timedelta(hours=25)), now)


async def test_run_sources_only_due_skips_recent_sources(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    await setup_sources(worker_engine, make_config)
    server = ScriptedServer(ok(rss(rss_item())))
    first = await run_sources(worker_engine, server.fetcher(), only_due=True)
    again = await run_sources(worker_engine, server.fetcher(), only_due=True)
    forced = await run_sources(worker_engine, server.fetcher(), only_due=False)
    assert (len(first), len(again), len(forced)) == (1, 0, 1)


# --- concurrency ---------------------------------------------------------------------------


async def test_overlapping_runs_for_the_same_source_are_prevented(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        started.set()
        await release.wait()
        return httpx.Response(200, content=rss(rss_item()))

    from worker.ingest.fetcher import FeedFetcher, FetchSettings

    slow = FeedFetcher(
        httpx.AsyncClient(transport=httpx.MockTransport(slow_handler)),
        FetchSettings(domain_min_interval_seconds=0.0),
    )
    first = asyncio.create_task(ingest_source(worker_engine, slow, src))
    await asyncio.wait_for(started.wait(), 10)

    # a second worker tries the same source while the first is mid-fetch
    second_server = ScriptedServer(ok(rss(rss_item())))
    second = await ingest_source(worker_engine, second_server.fetcher(), src)
    assert second.outcome == "skipped_locked"
    assert second_server.requests == []

    release.set()
    assert (await first).outcome == "success"
    # the lock is released afterwards
    third = await ingest_source(worker_engine, ScriptedServer(ok(rss(rss_item()))).fetcher(), src)
    assert third.outcome == "success"
    assert (await one(worker_engine, "SELECT count(*) FROM announcements"))[0] == 1
    assert (await one(worker_engine, "SELECT count(*) FROM sync_runs"))[0] == 2  # skipped = no row


async def test_different_sources_do_not_block_each_other(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    other = source(slug="acme-two", url="https://acme.test/feed2.xml")
    srcs = await setup_sources(worker_engine, make_config, acme=company(sources=[source(), other]))
    server = ScriptedServer(ok(rss(rss_item(link="https://acme.test/a"))))
    reports = await asyncio.gather(
        ingest_source(worker_engine, server.fetcher(), srcs[0]),
        ingest_source(
            worker_engine,
            ScriptedServer(ok(rss(rss_item(link="https://acme.test/b")))).fetcher(),
            srcs[1],
        ),
    )
    assert [r.outcome for r in reports] == ["success", "success"]


# --- permissions ---------------------------------------------------------------------------


async def test_worker_role_cannot_change_schema(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    await setup_sources(worker_engine, make_config)
    for sql in ("DROP TABLE announcements", "TRUNCATE announcements", "CREATE TABLE rogue (x int)"):
        with pytest.raises(DBAPIError):
            async with worker_engine.begin() as conn:
                await conn.execute(text(sql))


async def test_api_role_cannot_write_announcements_or_history(
    worker_engine: AsyncEngine, api_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    await ingest_source(worker_engine, ScriptedServer(ok(rss(rss_item()))).fetcher(), src)

    async with api_engine.connect() as conn:  # reads work
        assert (await conn.execute(text("SELECT count(*) FROM announcements"))).scalar_one() == 1
        assert (await conn.execute(text("SELECT count(*) FROM sync_runs"))).scalar_one() == 1
    for sql in (
        "DELETE FROM announcements",
        "UPDATE announcements SET title = 'x'",
        "INSERT INTO sync_runs (source_id, status) VALUES (1, 'running')",
        "UPDATE sources SET status = 'ok'",
    ):
        with pytest.raises(DBAPIError):
            async with api_engine.begin() as conn:
                await conn.execute(text(sql))
    assert (await one(worker_engine, "SELECT count(*) FROM announcements"))[0] == 1


async def test_ingestion_creates_nothing_but_announcements_and_history(
    worker_engine: AsyncEngine, make_config: Builder
) -> None:
    [src] = await setup_sources(worker_engine, make_config)
    await ingest_source(worker_engine, ScriptedServer(ok(rss(rss_item()))).fetcher(), src)
    for table in ("models", "model_versions", "announcement_models", "announcement_categories"):
        assert (await one(worker_engine, f"SELECT count(*) FROM {table}"))[0] == 0  # noqa: S608
