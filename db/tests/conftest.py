"""Test fixtures.

Tests run against DISPOSABLE databases (named modelradar_test_<random>) created on the
Postgres server given by TEST_DATABASE_ADMIN_URL and dropped afterwards. They never touch
the development database. The admin URL must use a superuser role (the compose owner
role is one), e.g.:

    postgresql+psycopg://modelradar_owner:<password>@localhost:5432/postgres
"""

import os
import secrets
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import URL, make_url

DB_DIR = Path(__file__).resolve().parent.parent
TEST_DB_PREFIX = "modelradar_test_"


def alembic_config(url: URL) -> Config:
    cfg = Config(str(DB_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(DB_DIR / "migrations"))
    rendered = url.render_as_string(hide_password=False).replace("%", "%%")
    cfg.set_main_option("sqlalchemy.url", rendered)
    return cfg


@pytest.fixture(scope="session")
def admin_url() -> URL:
    raw = os.environ.get("TEST_DATABASE_ADMIN_URL")
    if not raw:
        pytest.fail(
            "TEST_DATABASE_ADMIN_URL is not set. Point it at a Postgres server (superuser role, "
            "database 'postgres'); the tests create and drop their own disposable databases.",
            pytrace=False,
        )
    return make_url(raw)


@pytest.fixture(scope="session", autouse=True)
def app_roles(admin_url: URL) -> None:
    """Ensure the application roles exist (they already do in the compose stack)."""
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        for role in ("modelradar_worker", "modelradar_api"):
            exists = conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}
            ).scalar()
            if not exists:
                conn.execute(text(f"CREATE ROLE {role} NOLOGIN"))
    engine.dispose()


def _create_database(admin_url: URL) -> str:
    name = TEST_DB_PREFIX + secrets.token_hex(6)
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine.dispose()
    return name


def _drop_database(admin_url: URL, name: str) -> None:
    assert name.startswith(TEST_DB_PREFIX), "refusing to drop a non-test database"
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    engine.dispose()


@pytest.fixture
def empty_db_url(admin_url: URL) -> Iterator[URL]:
    """A brand-new empty disposable database."""
    name = _create_database(admin_url)
    try:
        yield admin_url.set(database=name)
    finally:
        _drop_database(admin_url, name)


@pytest.fixture(scope="session")
def migrated_db_url(admin_url: URL) -> Iterator[URL]:
    """A disposable database migrated to head, shared by read/constraint tests."""
    name = _create_database(admin_url)
    url = admin_url.set(database=name)
    try:
        command.upgrade(alembic_config(url), "head")
        yield url
    finally:
        _drop_database(admin_url, name)


@pytest.fixture
def conn(migrated_db_url: URL) -> Iterator[Connection]:
    """Owner connection inside a transaction that is always rolled back."""
    engine = create_engine(migrated_db_url)
    connection = engine.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()
