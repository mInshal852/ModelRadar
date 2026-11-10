"""Role separation checks.

Each test uses `SET LOCAL ROLE` inside a rolled-back transaction, so privileges are
evaluated exactly as for a login as that role, without needing the roles' passwords.
"""

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import ProgrammingError

from tests.helpers import insert_announcement, insert_company, insert_source, seed_announcement

APP_TABLES = [
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


def _denied(conn: Connection, role: str, sql: str) -> None:
    """The statement must be refused for `role` (missing privilege or not the owner)."""
    with (
        pytest.raises(ProgrammingError, match="permission denied|must be owner"),
        conn.begin_nested(),
    ):
        conn.execute(text(f"SET LOCAL ROLE {role}"))
        conn.execute(text(sql))


def test_roles_have_no_elevated_attributes(conn: Connection) -> None:
    rows = conn.execute(
        text(
            "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication "
            "FROM pg_roles WHERE rolname IN ('modelradar_worker', 'modelradar_api')"
        )
    ).all()
    assert {r.rolname for r in rows} == {"modelradar_worker", "modelradar_api"}
    for r in rows:
        assert not (r.rolsuper or r.rolcreatedb or r.rolcreaterole or r.rolreplication), r.rolname


@pytest.mark.parametrize("role", ["modelradar_worker", "modelradar_api"])
def test_no_schema_create_rights(conn: Connection, role: str) -> None:
    assert (
        conn.execute(
            text("SELECT has_schema_privilege(:r, 'public', 'CREATE')"), {"r": role}
        ).scalar()
        is False
    )
    _denied(conn, role, "CREATE TABLE rogue (id int)")


@pytest.mark.parametrize("table", APP_TABLES)
def test_api_can_read_every_table(conn: Connection, table: str) -> None:
    conn.execute(text("SET LOCAL ROLE modelradar_api"))
    assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0  # noqa: S608


@pytest.mark.parametrize("table", APP_TABLES)
def test_api_cannot_write_any_table(conn: Connection, table: str) -> None:
    column = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t ORDER BY ordinal_position LIMIT 1"
        ),
        {"t": table},
    ).scalar_one()
    _denied(conn, "modelradar_api", f"DELETE FROM {table}")  # noqa: S608
    _denied(conn, "modelradar_api", f"UPDATE {table} SET {column} = {column}")  # noqa: S608
    _denied(conn, "modelradar_api", f"TRUNCATE {table}")


def test_api_cannot_insert(conn: Connection) -> None:
    _denied(
        conn,
        "modelradar_api",
        "INSERT INTO companies (slug, name, website_url) VALUES ('x', 'X', 'https://x.test')",
    )


def test_api_cannot_use_sequences(conn: Connection) -> None:
    _denied(conn, "modelradar_api", "SELECT nextval(pg_get_serial_sequence('announcements', 'id'))")


def test_worker_can_do_required_operations(conn: Connection) -> None:
    conn.execute(text("SET LOCAL ROLE modelradar_worker"))
    company = insert_company(conn)  # INSERT (identity PK works without sequence grants)
    source = insert_source(conn, company)
    ann = insert_announcement(conn, company, source)
    conn.execute(text("UPDATE announcements SET title = 'Edited' WHERE id = :i"), {"i": ann})
    conn.execute(
        text("INSERT INTO sync_runs (source_id, status) VALUES (:s, 'success')"), {"s": source}
    )
    conn.execute(
        text("UPDATE sources SET status = 'ok', last_synced_at = now() WHERE id = :s"),
        {"s": source},
    )
    assert conn.execute(text("SELECT count(*) FROM announcements")).scalar_one() == 1
    conn.execute(text("DELETE FROM announcements WHERE id = :i"), {"i": ann})
    assert conn.execute(text("SELECT count(*) FROM announcements")).scalar_one() == 0


def test_worker_cannot_change_schema_or_truncate(conn: Connection) -> None:
    seed_announcement(conn)
    for sql in (
        "DROP TABLE announcements",
        "ALTER TABLE announcements ADD COLUMN x int",
        "TRUNCATE announcements",
        "CREATE INDEX rogue_idx ON announcements (title)",
    ):
        _denied(conn, "modelradar_worker", sql)


@pytest.mark.parametrize("role", ["modelradar_worker", "modelradar_api"])
def test_migration_bookkeeping_is_owner_only(conn: Connection, role: str) -> None:
    _denied(conn, role, "SELECT * FROM alembic_version")
    _denied(conn, role, "UPDATE alembic_version SET version_num = 'x'")
