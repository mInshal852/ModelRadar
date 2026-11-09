import re

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL

from modelradar_db.models import Base
from tests.conftest import alembic_config

EXPECTED_TABLES = {
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
}


EXPRESSION_INDEXES = {
    "ix_announcements_published_at",
    "ix_announcements_company_published",
    "ix_announcements_fts",
    "ix_sync_runs_source_started",
}


def _tables(url: URL) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_from_empty_database_creates_all_tables(empty_db_url: URL) -> None:
    assert _tables(empty_db_url) == set()
    command.upgrade(alembic_config(empty_db_url), "head")
    assert _tables(empty_db_url) == EXPECTED_TABLES | {"alembic_version"}


def test_version_is_tracked_and_matches_head(empty_db_url: URL) -> None:
    cfg = alembic_config(empty_db_url)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert head == "0001"

    command.upgrade(cfg, "head")
    engine = create_engine(empty_db_url)
    try:
        with engine.connect() as conn:
            assert MigrationContext.configure(conn).get_current_revision() == head
            rows = conn.execute(text("SELECT version_num FROM alembic_version")).all()
            assert [r[0] for r in rows] == [head]
    finally:
        engine.dispose()


def test_upgrade_is_idempotent(empty_db_url: URL) -> None:
    cfg = alembic_config(empty_db_url)
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # already at head: must be a no-op
    assert _tables(empty_db_url) == EXPECTED_TABLES | {"alembic_version"}


def test_downgrade_then_upgrade_is_repeatable(empty_db_url: URL) -> None:
    cfg = alembic_config(empty_db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert _tables(empty_db_url) == {"alembic_version"}
    command.upgrade(cfg, "head")
    assert _tables(empty_db_url) == EXPECTED_TABLES | {"alembic_version"}


def test_migrations_match_models(migrated_db_url: URL) -> None:
    """The migration and the SQLAlchemy models describe the same schema (no drift)."""
    engine = create_engine(migrated_db_url)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={"compare_type": True})
            diff = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()
    # Expression indexes are rendered differently by Postgres than they are written, so
    # Alembic always reports them as changed; they are verified by name below instead.
    unexpected = [
        d
        for d in diff
        if not (
            isinstance(d, tuple)
            and d[0] in {"add_index", "remove_index"}
            and d[1].name in EXPRESSION_INDEXES
        )
    ]
    assert unexpected == []


def test_expression_indexes_exist(migrated_db_url: URL) -> None:
    engine = create_engine(migrated_db_url)
    try:
        with engine.connect() as conn:
            names = {r[0] for r in conn.execute(text("SELECT indexname FROM pg_indexes"))}
    finally:
        engine.dispose()
    assert names >= EXPRESSION_INDEXES


def test_no_user_or_tracking_tables() -> None:
    """Privacy guard: the schema holds public announcement data only."""
    forbidden = re.compile(
        r"user|account|session|auth|login|password|token|profile|bookmark|favou?rite|"
        r"watchlist|preference|analytics|event|visit|tracking|subscriber",
        re.IGNORECASE,
    )
    assert not [t for t in EXPECTED_TABLES if forbidden.search(t)]
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    for table in Base.metadata.tables.values():
        assert not [c.name for c in table.columns if forbidden.search(c.name)], table.name
