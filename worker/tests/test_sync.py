"""Database synchronisation tests (disposable databases, real migrations).

Requires TEST_DATABASE_ADMIN_URL; see conftest.py.
"""

import datetime as dt
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_config_validation import company, source
from worker.sources.loader import LoadedConfig, load_config, validate_config_dir
from worker.sources.sync import sync_config

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"
Builder = Callable[..., Path]

# Tables the sync is allowed to write; everything else must stay empty.
SYNCED_TABLES = {"categories", "companies", "company_categories", "sources"}
ALL_TABLES = [
    "categories",
    "companies",
    "company_categories",
    "sources",
    "announcements",
    "announcement_categories",
    "models",
    "model_versions",
    "model_version_categories",
    "announcement_models",
    "sync_runs",
]


def small_config(make_config: Builder, **companies: dict[str, Any]) -> LoadedConfig:
    files = {f"{n}.yaml": yaml.safe_dump(d) for n, d in (companies or {"acme": company()}).items()}
    config, errors = validate_config_dir(make_config(companies=files), expected_top_level=None)
    assert config is not None, errors
    return config


async def count(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one())  # noqa: S608


async def run_sync(engine: AsyncEngine, config: LoadedConfig, role: str | None = None) -> Any:
    async with engine.begin() as conn:
        if role:
            await conn.execute(text(f"SET LOCAL ROLE {role}"))
        return await sync_config(conn, config)


# --- first run ---------------------------------------------------------------------------


async def test_first_sync_creates_everything_and_no_announcements(
    engine: AsyncEngine, make_config: Builder
) -> None:
    config = small_config(make_config)
    summary = await run_sync(engine, config)

    assert summary.categories.created == 3  # cat-one, cat-one-a, cat-two
    assert summary.companies.created == 1
    assert summary.sources.created == 1
    assert summary.company_category_links_added == 1
    for table in ALL_TABLES:
        if table not in SYNCED_TABLES:
            assert await count(engine, table) == 0, f"{table} must stay empty (no fabricated data)"


async def test_category_hierarchy_and_company_links(
    engine: AsyncEngine, make_config: Builder
) -> None:
    await run_sync(engine, small_config(make_config))
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT c.slug, p.slug AS parent FROM categories c "
                    "LEFT JOIN categories p ON p.id = c.parent_id ORDER BY c.slug"
                )
            )
        ).all()
        assert {(r.slug, r.parent) for r in rows} == {
            ("cat-one", None),
            ("cat-one-a", "cat-one"),
            ("cat-two", None),
        }
        link = (
            await conn.execute(
                text(
                    "SELECT k.slug FROM company_categories cc "
                    "JOIN categories k ON k.id = cc.category_id"
                )
            )
        ).scalar_one()
        assert link == "cat-one"


async def test_source_metadata_is_stored_faithfully(
    engine: AsyncEngine, make_config: Builder
) -> None:
    rules = {"include_categories": ["Product"]}
    src = source(
        hosting="official_third_party",
        hosting_notes="Hosted on a partner domain.",
        content_scope="mixed",
        relevance_rules=rules,
    )
    config = small_config(make_config, acme=company(official_domains=["acme.test"], sources=[src]))
    await run_sync(engine, config)
    async with engine.connect() as conn:
        row = (await conn.execute(text("SELECT * FROM sources"))).mappings().one()
    assert (row["kind"], row["url"]) == ("rss", "https://acme.test/feed.xml")
    assert (row["hosting"], row["content_scope"]) == ("official_third_party", "mixed")
    assert row["hosting_notes"] == "Hosted on a partner domain."
    assert row["verification_level"] == "content_sampled"
    assert row["verified_at"] == dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    assert row["poll_interval_minutes"] == 60
    stored_rules = row["relevance_rules"]
    stored_rules = json.loads(stored_rules) if isinstance(stored_rules, str) else stored_rules
    assert stored_rules["include_categories"] == ["Product"]
    assert row["extractor_config"] is None
    assert row["status"] is None  # never synced: unknown
    # runtime fields untouched
    assert (row["etag"], row["last_synced_at"], row["last_error"]) == (None, None, None)
    assert row["consecutive_failures"] == 0


async def test_company_optional_fields_stay_null(engine: AsyncEngine, make_config: Builder) -> None:
    await run_sync(engine, small_config(make_config))
    async with engine.connect() as conn:
        row = (await conn.execute(text("SELECT country, description FROM companies"))).one()
    assert (row.country, row.description) == (None, None)


# --- idempotency -------------------------------------------------------------------------


async def test_second_sync_changes_nothing(engine: AsyncEngine, make_config: Builder) -> None:
    config = small_config(make_config)
    await run_sync(engine, config)
    before = {t: await count(engine, t) for t in ALL_TABLES}

    summary = await run_sync(engine, config)
    assert summary.categories.unchanged == 3 and summary.categories.created == 0
    assert (summary.companies.unchanged, summary.sources.unchanged) == (1, 1)
    assert summary.company_category_links_added == 0
    assert summary.warnings == []
    assert {t: await count(engine, t) for t in ALL_TABLES} == before


async def test_repeated_runs_never_duplicate_real_config(engine: AsyncEngine) -> None:
    config = load_config(REPO_CONFIG)
    first = await run_sync(engine, config)
    assert first.sources.created == 11 and first.companies.created == 10
    assert first.categories.created > 17  # 17 parents plus children
    ids_before = await _ids(engine)

    for _ in range(2):
        again = await run_sync(engine, config)
        assert again.categories.created == again.companies.created == again.sources.created == 0
        assert again.categories.updated == again.companies.updated == again.sources.updated == 0
    assert await _ids(engine) == ids_before
    assert await count(engine, "announcements") == 0


async def _ids(engine: AsyncEngine) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    async with engine.connect() as conn:
        for table in ("categories", "companies", "sources"):
            rows = await conn.execute(text(f"SELECT id FROM {table} ORDER BY id"))  # noqa: S608
            out[table] = [r[0] for r in rows]
    return out


async def test_real_config_disabled_source_is_marked_disabled(engine: AsyncEngine) -> None:
    await run_sync(engine, load_config(REPO_CONFIG))
    async with engine.connect() as conn:
        rows = (
            await conn.execute(text("SELECT url, status, verification_notes FROM sources"))
        ).all()
    by_status = {r.status for r in rows}
    assert by_status == {None, "disabled"}
    disabled = [r for r in rows if r.status == "disabled"]
    assert len(disabled) == 1 and disabled[0].verification_notes.startswith("DISABLED: ")


# --- config changes and preservation of existing data --------------------------------------


async def test_config_edits_are_applied_as_updates(
    engine: AsyncEngine, make_config: Builder
) -> None:
    await run_sync(engine, small_config(make_config))
    changed = company(name="Acme Intelligence", sources=[source(poll_interval_minutes=120)])
    summary = await run_sync(engine, small_config(make_config, acme=changed))
    assert (summary.companies.updated, summary.sources.updated) == (1, 1)
    async with engine.connect() as conn:
        assert (
            await conn.execute(text("SELECT name FROM companies"))
        ).scalar_one() == "Acme Intelligence"
        assert (
            await conn.execute(text("SELECT poll_interval_minutes FROM sources"))
        ).scalar_one() == 120


async def test_runtime_fields_survive_resync(engine: AsyncEngine, make_config: Builder) -> None:
    config = small_config(make_config)
    await run_sync(engine, config)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE sources SET etag = 'abc', last_modified = 'yesterday', status = 'ok', "
                "last_synced_at = now(), last_error = 'old', consecutive_failures = 2"
            )
        )
    summary = await run_sync(engine, config)
    assert summary.sources.unchanged == 1
    async with engine.connect() as conn:
        row = (await conn.execute(text("SELECT * FROM sources"))).mappings().one()
    assert (row["etag"], row["last_modified"], row["status"]) == ("abc", "yesterday", "ok")
    assert row["last_synced_at"] is not None
    assert (row["last_error"], row["consecutive_failures"]) == ("old", 2)


async def test_disable_and_reenable_source(engine: AsyncEngine, make_config: Builder) -> None:
    await run_sync(engine, small_config(make_config))
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE sources SET status = 'ok'"))

    off = source(enabled=False, disabled_reason="Blocked by the publisher.")
    await run_sync(engine, small_config(make_config, acme=company(sources=[off])))
    async with engine.connect() as conn:
        row = (await conn.execute(text("SELECT status, verification_notes FROM sources"))).one()
    assert row.status == "disabled"
    assert "Blocked by the publisher." in row.verification_notes

    await run_sync(engine, small_config(make_config))  # enabled again
    async with engine.connect() as conn:
        row = (await conn.execute(text("SELECT status, verification_notes FROM sources"))).one()
    assert row.status is None  # re-enabled sources start as never synced
    assert not row.verification_notes.startswith("DISABLED")


async def test_nothing_is_deleted_and_announcements_are_preserved(
    engine: AsyncEngine, make_config: Builder
) -> None:
    config = small_config(make_config)
    await run_sync(engine, config)
    async with engine.begin() as conn:
        ids = (await conn.execute(text("SELECT c.id, s.id FROM companies c, sources s"))).one()
        await conn.execute(
            text(
                "INSERT INTO announcements (company_id, source_id, title, original_url, "
                "content_hash) VALUES (:c, :s, 'Existing', 'https://acme.test/x', 'h')"
            ),
            {"c": ids[0], "s": ids[1]},
        )
        # rows that the config does not know about
        await conn.execute(
            text(
                "INSERT INTO companies (slug, name, website_url) VALUES ('old', 'Old', 'https://old.test')"
            )
        )

    # config now drops the category link and the source URL changes
    moved = company(categories=["cat-two"], sources=[source(url="https://acme.test/new.xml")])
    summary = await run_sync(engine, small_config(make_config, acme=moved))

    assert await count(engine, "announcements") == 1
    assert await count(engine, "companies") == 2
    assert await count(engine, "sources") == 2  # old URL kept, new URL added
    assert await count(engine, "company_categories") == 2  # stale link kept, new one added
    text_warnings = " ".join(summary.warnings)
    assert "no longer in the config" in text_warnings
    assert "not in the config (kept)" in text_warnings
    assert "'old'" in text_warnings


# --- permissions -------------------------------------------------------------------------


async def test_sync_works_with_the_worker_role_only(
    engine: AsyncEngine, make_config: Builder
) -> None:
    """The sync must not need owner privileges: it runs as modelradar_worker."""
    config = small_config(make_config)
    first = await run_sync(engine, config, role="modelradar_worker")
    assert first.sources.created == 1
    second = await run_sync(engine, config, role="modelradar_worker")
    assert second.sources.unchanged == 1


async def test_api_role_cannot_run_the_sync(engine: AsyncEngine, make_config: Builder) -> None:
    import pytest
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        await run_sync(engine, small_config(make_config), role="modelradar_api")
    assert await count(engine, "companies") == 0
