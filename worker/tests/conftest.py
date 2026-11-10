"""Shared fixtures.

Database tests create DISPOSABLE databases (modelradar_test_<random>) on the Postgres server
given by TEST_DATABASE_ADMIN_URL (a superuser, database 'postgres'), apply the real
migrations from db/, and drop the database afterwards. They never touch the development
database.

    postgresql+psycopg://modelradar_owner:<password>@localhost:5432/postgres
"""

import os
import secrets
import shutil
import textwrap
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_DIR = REPO_ROOT / "db"
TEST_DB_PREFIX = "modelradar_test_"


@pytest.fixture(scope="session")
def admin_url() -> URL:
    raw = os.environ.get("TEST_DATABASE_ADMIN_URL")
    if not raw:
        pytest.fail(
            "TEST_DATABASE_ADMIN_URL is not set (superuser URL, database 'postgres'). "
            "Database tests create and drop their own disposable databases.",
            pytrace=False,
        )
    return make_url(raw)


@pytest.fixture(scope="session", autouse=True)
def app_roles() -> None:
    """Ensure the application roles exist (they already do in the compose stack).

    Skipped when no database is configured, so the non-database tests run anywhere.
    """
    raw = os.environ.get("TEST_DATABASE_ADMIN_URL")
    if not raw:
        return
    engine = create_engine(make_url(raw), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        for role in ("modelradar_worker", "modelradar_api"):
            if not conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}
            ).scalar():
                conn.execute(text(f"CREATE ROLE {role} NOLOGIN"))
    engine.dispose()


def _alembic_config(url: URL) -> Config:
    cfg = Config(str(DB_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(DB_DIR / "migrations"))
    cfg.set_main_option("prepend_sys_path", str(DB_DIR))
    cfg.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    return cfg


@pytest.fixture
def migrated_db_url(admin_url: URL) -> Iterator[URL]:
    """A fresh disposable database migrated to head (psycopg URL)."""
    name = TEST_DB_PREFIX + secrets.token_hex(6)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = admin_url.set(database=name)
    try:
        command.upgrade(_alembic_config(url), "head")
        yield url
    finally:
        assert name.startswith(TEST_DB_PREFIX)
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest_asyncio.fixture
async def engine(migrated_db_url: URL) -> AsyncIterator[AsyncEngine]:
    async_engine = create_async_engine(migrated_db_url.set(drivername="postgresql+asyncpg"))
    try:
        yield async_engine
    finally:
        await async_engine.dispose()


# --- config directory builder (synthetic YAML used only by tests) --------------------------

CATEGORIES_YAML = """
categories:
  - slug: cat-one
    name: Category One
    children:
      - {slug: cat-one-a, name: One A}
  - slug: cat-two
    name: Category Two
"""

COMPANY_YAML = """
slug: acme
name: Acme AI
website_url: https://acme.test
categories: [cat-one]
sources:
  - slug: acme-blog
    name: Acme blog
    kind: rss
    url: https://acme.test/feed.xml
    hosting: first_party
    content_scope: dedicated_ai
    verification_level: content_sampled
    verified_at: 2026-01-01
    verification_notes: Test fixture source.
    poll_interval_minutes: 60
"""


@pytest.fixture
def make_config(tmp_path: Path) -> Callable[..., Path]:
    """Build a temporary config dir. Pass `companies={filename: yaml}` to override."""

    def build(
        categories: str = CATEGORIES_YAML,
        companies: dict[str, str] | None = None,
    ) -> Path:
        root = tmp_path / "config"
        shutil.rmtree(root, ignore_errors=True)  # allow several builds per test
        (root / "companies").mkdir(parents=True)
        (root / "categories.yaml").write_text(textwrap.dedent(categories), encoding="utf-8")
        for filename, body in (companies or {"acme.yaml": COMPANY_YAML}).items():
            (root / "companies" / filename).write_text(textwrap.dedent(body), encoding="utf-8")
        return root

    return build
