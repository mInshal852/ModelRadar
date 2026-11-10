"""API test fixtures.

Database tests create a DISPOSABLE database (modelradar_test_<random>), apply the real
migrations from db/, load SYNTHETIC rows that exist only for these tests, and drop it again.
They never touch the development database. Set TEST_DATABASE_ADMIN_URL to a superuser URL of
a Postgres server (database 'postgres'):

    postgresql+psycopg://modelradar_owner:<password>@localhost:5432/postgres

The API under test connects as the read-only modelradar_api role, like in production.
"""

import datetime as dt
import os
import secrets
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.db import get_connection
from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_DIR = REPO_ROOT / "db"
TEST_DB_PREFIX = "modelradar_test_"
UTC = dt.UTC


def _alembic_config(url: URL) -> Config:
    cfg = Config(str(DB_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(DB_DIR / "migrations"))
    cfg.set_main_option("prepend_sys_path", str(DB_DIR))
    cfg.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    return cfg


@pytest.fixture(scope="session")
def admin_url() -> URL:
    raw = os.environ.get("TEST_DATABASE_ADMIN_URL")
    if not raw:
        pytest.fail(
            "TEST_DATABASE_ADMIN_URL is not set (superuser URL, database 'postgres').",
            pytrace=False,
        )
    return make_url(raw)


@pytest.fixture(scope="session")
def seeded_db_url(admin_url: URL) -> Iterator[URL]:
    """Disposable migrated database with synthetic rows (read by the API tests)."""
    name = TEST_DB_PREFIX + secrets.token_hex(6)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        for role in ("modelradar_worker", "modelradar_api"):
            if not conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}
            ).scalar():
                conn.execute(text(f"CREATE ROLE {role} NOLOGIN"))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = admin_url.set(database=name)
    try:
        command.upgrade(_alembic_config(url), "head")
        engine = create_engine(url)
        with engine.begin() as conn:
            seed(conn)
        engine.dispose()
        yield url
    finally:
        assert name.startswith(TEST_DB_PREFIX)
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def seed(conn: object) -> None:
    """Synthetic fixture rows. Names are obviously fake and live only in the test database."""
    from sqlalchemy import Connection

    assert isinstance(conn, Connection)

    def one(sql: str, **p: object) -> int:
        return int(conn.execute(text(sql), p).scalar_one())

    cat_a = one(
        "INSERT INTO categories (slug, name, sort_order) VALUES ('cat-a','Category A',0) RETURNING id"
    )
    cat_a1 = one(
        "INSERT INTO categories (slug, name, parent_id, sort_order) VALUES ('cat-a1','Category A1',:p,0) RETURNING id",
        p=cat_a,
    )
    cat_b = one(
        "INSERT INTO categories (slug, name, sort_order) VALUES ('cat-b','Category B',1) RETURNING id"
    )

    acme = one(
        "INSERT INTO companies (slug, name, website_url, country, description) "
        "VALUES ('acme','Acme Labs','https://acme.test','US','Test company.') RETURNING id"
    )
    beta = one(
        "INSERT INTO companies (slug, name, website_url) VALUES ('beta','Beta Works','https://beta.test') RETURNING id"
    )
    one(
        "INSERT INTO companies (slug, name, website_url) VALUES ('gamma','Gamma Unlimited','https://gamma.test') RETURNING id"
    )
    conn.execute(text("INSERT INTO company_categories VALUES (:c, :k)"), {"c": acme, "k": cat_a1})
    conn.execute(text("INSERT INTO company_categories VALUES (:c, :k)"), {"c": beta, "k": cat_b})

    def source(
        company: int,
        name: str,
        url: str,
        status: str | None,
        error: str | None = None,
        synced: bool = False,
    ) -> int:
        return one(
            "INSERT INTO sources (company_id, name, kind, url, hosting, content_scope, verification_level, "
            "verification_notes, poll_interval_minutes, status, last_error, consecutive_failures, "
            "last_synced_at, etag, extractor_config) VALUES (:c, :n, 'rss', :u, 'first_party', 'mixed', "
            "'content_sampled', 'Inspected in tests.', 60, :s, :e, :f, :ls, 'secret-etag', "
            "CAST('{\"internal\": true}' AS jsonb)) RETURNING id",
            c=company,
            n=name,
            u=url,
            s=status,
            e=error,
            f=3 if status == "failing" else 0,
            ls=dt.datetime(2026, 11, 8, 9, 0, tzinfo=UTC) if synced else None,
        )

    s_acme = source(acme, "Acme feed", "https://acme.test/feed.xml", "ok", synced=True)
    s_beta = source(beta, "Beta feed", "https://beta.test/feed.xml", "failing", "HTTP 403")
    source(beta, "Beta old feed", "https://beta.test/old.xml", "disabled")
    source(
        beta,
        "Beta broken",
        "https://beta.test/broken.xml",
        "degraded",
        "processing failed: RuntimeError: secret detail",
    )
    source(acme, "Acme never synced", "https://acme.test/new.xml", None)
    conn.execute(
        text(
            "INSERT INTO sync_runs (source_id, started_at, finished_at, status, http_status, "
            "items_found, items_new, items_filtered) VALUES "
            "(:s, '2026-11-08 09:00+00', '2026-11-08 09:00:05+00', 'success', 200, 7, 4, 1)"
        ),
        {"s": s_acme},
    )
    conn.execute(
        text(
            "INSERT INTO sync_runs (source_id, started_at, finished_at, status, http_status, error) "
            "VALUES (:s, '2026-11-08 09:30+00', '2026-11-08 09:30:01+00', 'failed', 403, 'HTTP 403')"
        ),
        {"s": s_beta},
    )

    def announcement(
        company: int,
        src: int,
        title: str,
        url: str,
        published: str | None,
        precision: str | None,
        description: str | None = None,
        kind: str = "other",
    ) -> int:
        return one(
            "INSERT INTO announcements (company_id, source_id, title, description, kind, published_at, "
            "published_precision, original_url, content_hash) VALUES (:c,:s,:t,:d,:k,:p,:pp,:u,'h') RETURNING id",
            c=company,
            s=src,
            t=title,
            d=description,
            k=kind,
            p=published,
            pp=precision,
            u=url,
        )

    a1 = announcement(
        acme,
        s_acme,
        "Alpha model released",
        "https://acme.test/alpha",
        "2026-11-05T10:30:00+00",
        "datetime",
        "Alpha is a new model.",
        "model_release",
    )
    announcement(
        acme,
        s_acme,
        "Notes without a time",
        "https://acme.test/notes",
        "2026-11-05T00:00:00+00",
        "day",
    )
    announcement(
        acme,
        s_acme,
        "Undated post",
        "https://acme.test/undated",
        None,
        None,
        "No date was published.",
    )
    a4 = announcement(
        acme,
        s_acme,
        "Delta research paper",
        "https://acme.test/delta",
        "2026-10-01T08:00:00+00",
        "datetime",
        "A study.",
        "research",
    )
    announcement(
        beta,
        s_beta,
        "Epsilon launch",
        "https://beta.test/epsilon",
        "2026-11-06T12:00:00+00",
        "datetime",
        None,
        "model_release",
    )
    announcement(
        beta,
        s_beta,
        "Discount 100% off_now",
        "https://beta.test/discount",
        "2026-09-01T00:00:00+00",
        "day",
    )
    for n in range(25):
        announcement(
            beta,
            s_beta,
            f"Filler item {n:02d}",
            f"https://beta.test/filler/{n}",
            (dt.datetime(2026, 8, 1, tzinfo=UTC) - dt.timedelta(days=n)).isoformat(),
            "datetime",
        )
    # One announcement with its OWN category: it must not inherit the company's.
    conn.execute(text("INSERT INTO announcement_categories VALUES (:a, :k)"), {"a": a4, "k": cat_b})

    model = one(
        "INSERT INTO models (company_id, slug, family_name) VALUES (:c,'alpha','Alpha') RETURNING id",
        c=acme,
    )
    version = one(
        "INSERT INTO model_versions (model_id, version_label, display_name, first_announced_at, "
        "first_announced_precision, first_announcement_id) VALUES (:m,'1','Alpha 1', "
        "'2026-11-05T10:30:00+00','datetime',:a) RETURNING id",
        m=model,
        a=a1,
    )
    conn.execute(
        text("INSERT INTO announcement_models VALUES (:a, :v, 'Alpha 1')"), {"a": a1, "v": version}
    )
    conn.execute(
        text("INSERT INTO model_version_categories VALUES (:v, :k)"), {"v": version, "k": cat_a1}
    )


@pytest_asyncio.fixture(scope="session")
async def api_engine(seeded_db_url: URL) -> AsyncIterator[AsyncEngine]:
    """Acts as the read-only modelradar_api role with read-only sessions, like production."""
    engine = create_async_engine(
        seeded_db_url.set(drivername="postgresql+asyncpg"),
        connect_args={
            "server_settings": {
                "role": "modelradar_api",
                "default_transaction_read_only": "on",
                "statement_timeout": "5000",
            }
        },
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def client(api_engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    async def override() -> AsyncIterator[AsyncConnection]:
        async with api_engine.connect() as conn:
            yield conn

    app.dependency_overrides[get_connection] = override
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_connection, None)
