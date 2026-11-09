import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from tests.helpers import insert_announcement, insert_company, insert_source, seed_announcement


def _fails(conn: Connection, sql: str, params: dict[str, object] | None = None) -> None:
    """Assert the statement violates a constraint, leaving the transaction usable."""
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(text(sql), params or {})


# --- announcements: unique URL, dates, precision ------------------------------------------


def test_original_url_is_unique(conn: Connection) -> None:
    company, source, _ = seed_announcement(conn)
    with pytest.raises(IntegrityError), conn.begin_nested():
        insert_announcement(conn, company, source)  # same default original_url


def test_published_at_may_be_null_and_first_seen_is_separate(conn: Connection) -> None:
    company = insert_company(conn)
    source = insert_source(conn, company)
    ann = insert_announcement(conn, company, source, published_at=None, precision=None)
    row = conn.execute(
        text(
            "SELECT published_at, published_precision, first_seen_at FROM announcements WHERE id=:i"
        ),
        {"i": ann},
    ).one()
    assert row.published_at is None
    assert row.published_precision is None
    assert row.first_seen_at is not None  # recorded independently of the publication date


def test_old_publication_date_is_preserved_not_replaced_by_discovery(conn: Connection) -> None:
    company = insert_company(conn)
    source = insert_source(conn, company)
    ann = insert_announcement(
        conn, company, source, published_at="2019-02-14T00:00:00+00", precision="day"
    )
    row = conn.execute(
        text("SELECT published_at < first_seen_at AS older FROM announcements WHERE id=:i"),
        {"i": ann},
    ).one()
    assert row.older is True


@pytest.mark.parametrize("precision", ["day", "datetime"])
def test_valid_precisions_accepted(conn: Connection, precision: str) -> None:
    company = insert_company(conn)
    source = insert_source(conn, company)
    ann = insert_announcement(
        conn, company, source, published_at="2024-05-01T10:30:00+00", precision=precision
    )
    stored = conn.execute(
        text("SELECT published_precision FROM announcements WHERE id=:i"), {"i": ann}
    ).scalar_one()
    assert stored == precision


def test_precision_requires_a_date_and_vice_versa(conn: Connection) -> None:
    company = insert_company(conn)
    source = insert_source(conn, company)
    with pytest.raises(IntegrityError), conn.begin_nested():
        insert_announcement(conn, company, source, "https://e.test/a", None, "day")
    with pytest.raises(IntegrityError), conn.begin_nested():
        insert_announcement(
            conn, company, source, "https://e.test/b", "2024-05-01T00:00:00+00", None
        )


def test_invalid_precision_rejected(conn: Connection) -> None:
    company = insert_company(conn)
    source = insert_source(conn, company)
    with pytest.raises(IntegrityError), conn.begin_nested():
        insert_announcement(
            conn, company, source, "https://e.test/c", "2024-05-01T00:00:00+00", "minute"
        )


def test_unknown_values_stay_null_and_defaults_are_honest(conn: Connection) -> None:
    _, _, ann = seed_announcement(conn)
    row = conn.execute(
        text("SELECT description, metadata, kind FROM announcements WHERE id=:i"), {"i": ann}
    ).one()
    assert row.description is None
    assert row.metadata is None
    assert row.kind == "other"  # unclassified items are 'other', never promoted


def test_invalid_announcement_kind_rejected(conn: Connection) -> None:
    company = insert_company(conn)
    source = insert_source(conn, company)
    _fails(
        conn,
        "INSERT INTO announcements (company_id, source_id, title, kind, original_url, content_hash)"
        " VALUES (:c, :s, 't', 'press_release', 'https://e.test/k', 'h')",
        {"c": company, "s": source},
    )


# --- sources ------------------------------------------------------------------------------


def test_source_defaults_and_jsonb_roundtrip(conn: Connection) -> None:
    company = insert_company(conn)
    source = insert_source(conn, company)
    row = conn.execute(
        text(
            "SELECT verification_level, status, consecutive_failures, relevance_rules FROM sources"
            " WHERE id=:i"
        ),
        {"i": source},
    ).one()
    assert row.verification_level == "http_only"
    assert row.status is None  # never synced: unknown, not 'ok'
    assert row.consecutive_failures == 0
    assert row.relevance_rules is None

    conn.execute(
        text("UPDATE sources SET relevance_rules = CAST(:r AS jsonb) WHERE id=:i"),
        {"r": '{"include_title": ["Copilot"]}', "i": source},
    )
    stored = conn.execute(
        text("SELECT relevance_rules FROM sources WHERE id=:i"), {"i": source}
    ).scalar_one()
    assert stored == {"include_title": ["Copilot"]}


@pytest.mark.parametrize(
    "column,value",
    [
        ("kind", "carrier_pigeon"),
        ("hosting", "self_hosted"),
        ("content_scope", "everything"),
        ("verification_level", "trust_me"),
        ("status", "great"),
        ("poll_interval_minutes", 0),
        ("consecutive_failures", -1),
    ],
)
def test_source_check_constraints(conn: Connection, column: str, value: object) -> None:
    company = insert_company(conn)
    source = insert_source(conn, company)
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(
            text(f"UPDATE sources SET {column} = :v WHERE id = :i"),  # column is test-controlled
            {"v": value, "i": source},
        )


def test_source_url_unique_per_company(conn: Connection) -> None:
    company = insert_company(conn)
    insert_source(conn, company, "https://e.test/feed")
    with pytest.raises(IntegrityError), conn.begin_nested():
        insert_source(conn, company, "https://e.test/feed")


# --- unique slugs and hierarchy -----------------------------------------------------------


def test_unique_slugs(conn: Connection) -> None:
    insert_company(conn, "dup")
    with pytest.raises(IntegrityError), conn.begin_nested():
        insert_company(conn, "dup")
    conn.execute(text("INSERT INTO categories (slug, name) VALUES ('c1', 'C1')"))
    _fails(conn, "INSERT INTO categories (slug, name) VALUES ('c1', 'Other')")


def test_category_parent_rules(conn: Connection) -> None:
    parent = conn.execute(
        text("INSERT INTO categories (slug, name) VALUES ('p', 'P') RETURNING id")
    ).scalar_one()
    child = conn.execute(
        text("INSERT INTO categories (slug, name, parent_id) VALUES ('ch', 'Ch', :p) RETURNING id"),
        {"p": parent},
    ).scalar_one()
    # A category cannot be its own parent.
    _fails(conn, "UPDATE categories SET parent_id = id WHERE id = :i", {"i": parent})
    # A parent with children cannot be deleted (RESTRICT).
    _fails(conn, "DELETE FROM categories WHERE id = :i", {"i": parent})
    assert child  # child row exists


# --- foreign keys -------------------------------------------------------------------------


def test_announcement_requires_existing_company_and_source(conn: Connection) -> None:
    company = insert_company(conn)
    source = insert_source(conn, company)
    _fails(
        conn,
        "INSERT INTO announcements (company_id, source_id, title, original_url, content_hash)"
        " VALUES (999999, :s, 't', 'https://e.test/x', 'h')",
        {"s": source},
    )
    _fails(
        conn,
        "INSERT INTO announcements (company_id, source_id, title, original_url, content_hash)"
        " VALUES (:c, 999999, 't', 'https://e.test/y', 'h')",
        {"c": company},
    )


def test_company_and_source_with_announcements_cannot_be_deleted(conn: Connection) -> None:
    company, source, _ = seed_announcement(conn)
    _fails(conn, "DELETE FROM sources WHERE id = :i", {"i": source})
    _fails(conn, "DELETE FROM companies WHERE id = :i", {"i": company})


def test_link_tables_cascade(conn: Connection) -> None:
    company, _, ann = seed_announcement(conn)
    cat = conn.execute(
        text("INSERT INTO categories (slug, name) VALUES ('x', 'X') RETURNING id")
    ).scalar_one()
    conn.execute(text("INSERT INTO announcement_categories VALUES (:a, :c)"), {"a": ann, "c": cat})
    conn.execute(text("INSERT INTO company_categories VALUES (:co, :c)"), {"co": company, "c": cat})
    # duplicate link rejected by the composite primary key
    _fails(conn, "INSERT INTO announcement_categories VALUES (:a, :c)", {"a": ann, "c": cat})

    conn.execute(text("DELETE FROM categories WHERE id = :c"), {"c": cat})
    assert conn.execute(text("SELECT count(*) FROM announcement_categories")).scalar_one() == 0
    assert conn.execute(text("SELECT count(*) FROM company_categories")).scalar_one() == 0


# --- models and versions ------------------------------------------------------------------


def _model_version(
    conn: Connection, company: int, ann: int, name: str = "Alpha 1"
) -> tuple[int, int]:
    model = conn.execute(
        text(
            "INSERT INTO models (company_id, slug, family_name) VALUES (:c, 'alpha', 'Alpha')"
            " RETURNING id"
        ),
        {"c": company},
    ).scalar_one()
    version = conn.execute(
        text(
            "INSERT INTO model_versions (model_id, display_name, first_announcement_id)"
            " VALUES (:m, :n, :a) RETURNING id"
        ),
        {"m": model, "n": name, "a": ann},
    ).scalar_one()
    return model, version


def test_model_version_provenance_and_nullable_fields(conn: Connection) -> None:
    company, _, ann = seed_announcement(conn)
    _, version = _model_version(conn, company, ann)
    row = conn.execute(
        text(
            "SELECT version_label, first_announced_at, first_announced_precision"
            " FROM model_versions WHERE id=:i"
        ),
        {"i": version},
    ).one()
    assert (row.version_label, row.first_announced_at, row.first_announced_precision) == (
        None,
        None,
        None,
    )
    # every version must reference an official announcement
    _fails(
        conn,
        "INSERT INTO model_versions (model_id, display_name) VALUES (1, 'No source')",
    )


def test_model_uniqueness(conn: Connection) -> None:
    company, _, ann = seed_announcement(conn)
    model, _ = _model_version(conn, company, ann)
    _fails(
        conn,
        "INSERT INTO models (company_id, slug, family_name) VALUES (:c, 'alpha', 'Dup')",
        {"c": company},
    )
    _fails(
        conn,
        "INSERT INTO model_versions (model_id, display_name, first_announcement_id)"
        " VALUES (:m, 'Alpha 1', :a)",
        {"m": model, "a": ann},
    )


def test_model_version_precision_pair(conn: Connection) -> None:
    company, _, ann = seed_announcement(conn)
    model, _ = _model_version(conn, company, ann)
    _fails(
        conn,
        "INSERT INTO model_versions (model_id, display_name, first_announced_at,"
        " first_announcement_id) VALUES (:m, 'Alpha 2', now(), :a)",
        {"m": model, "a": ann},
    )


def test_announcement_models_link(conn: Connection) -> None:
    company, _, ann = seed_announcement(conn)
    _, version = _model_version(conn, company, ann)
    conn.execute(
        text("INSERT INTO announcement_models VALUES (:a, :v, 'Alpha 1')"), {"a": ann, "v": version}
    )
    _fails(conn, "INSERT INTO announcement_models VALUES (:a, :v, NULL)", {"a": ann, "v": version})
    # a version's provenance announcement cannot be deleted while referenced (RESTRICT)
    _fails(conn, "DELETE FROM announcements WHERE id = :a", {"a": ann})


# --- sync runs ----------------------------------------------------------------------------


def test_sync_runs(conn: Connection) -> None:
    company = insert_company(conn)
    source = insert_source(conn, company)
    run = conn.execute(
        text("INSERT INTO sync_runs (source_id, status) VALUES (:s, 'running') RETURNING id"),
        {"s": source},
    ).scalar_one()
    row = conn.execute(
        text(
            "SELECT items_found, items_new, items_filtered, finished_at, http_status, error"
            " FROM sync_runs WHERE id=:i"
        ),
        {"i": run},
    ).one()
    assert tuple(row) == (0, 0, 0, None, None, None)
    _fails(conn, "INSERT INTO sync_runs (source_id, status) VALUES (:s, 'maybe')", {"s": source})
    _fails(
        conn,
        "INSERT INTO sync_runs (source_id, status, items_new) VALUES (:s, 'success', -1)",
        {"s": source},
    )
    _fails(conn, "INSERT INTO sync_runs (source_id, status) VALUES (999999, 'success')")
    # runs are removed together with their source
    conn.execute(text("DELETE FROM sources WHERE id = :s"), {"s": source})
    assert conn.execute(text("SELECT count(*) FROM sync_runs")).scalar_one() == 0
