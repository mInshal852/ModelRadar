"""Initial ModelRadar schema: public announcement data only.

Revision ID: 0001
Revises:
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Order matters for drops (children first).
TABLES = (
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
)


def _id() -> sa.Column[int]:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True)


def _tstz(name: str, **kw: object) -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)  # type: ignore[arg-type]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "categories",
        _id(),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), sa.ForeignKey("categories.id", ondelete="RESTRICT")),
        sa.Column("description", sa.Text()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("slug", name="uq_categories_slug"),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_categories_not_own_parent"),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])

    op.create_table(
        "companies",
        _id(),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("website_url", sa.Text(), nullable=False),
        sa.Column("country", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.UniqueConstraint("slug", name="uq_companies_slug"),
    )

    op.create_table(
        "company_categories",
        sa.Column(
            "company_id",
            sa.BigInteger(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "category_id",
            sa.BigInteger(),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("ix_company_categories_category_id", "company_categories", ["category_id"])

    op.create_table(
        "sources",
        _id(),
        sa.Column(
            "company_id",
            sa.BigInteger(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("hosting", sa.Text(), nullable=False),
        sa.Column("hosting_notes", sa.Text()),
        sa.Column("content_scope", sa.Text(), nullable=False),
        sa.Column(
            "verification_level",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'http_only'"),
        ),
        _tstz("verified_at"),
        sa.Column("verification_notes", sa.Text()),
        sa.Column("relevance_rules", postgresql.JSONB()),
        sa.Column("extractor_config", postgresql.JSONB()),
        sa.Column("poll_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("etag", sa.Text()),
        sa.Column("last_modified", sa.Text()),
        _tstz("last_synced_at"),
        sa.Column("status", sa.Text()),
        sa.Column("last_error", sa.Text()),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("company_id", "url", name="uq_sources_company_id_url"),
        sa.CheckConstraint(
            "kind IN ('rss', 'atom', 'github', 'api', 'sitemap', 'html', 'manual')",
            name="ck_sources_kind",
        ),
        sa.CheckConstraint(
            "hosting IN ('first_party', 'official_third_party')", name="ck_sources_hosting"
        ),
        sa.CheckConstraint(
            "content_scope IN ('dedicated_ai', 'mixed')", name="ck_sources_content_scope"
        ),
        sa.CheckConstraint(
            "verification_level IN ('http_only', 'content_sampled', 'content_verified')",
            name="ck_sources_verification_level",
        ),
        sa.CheckConstraint(
            "status IS NULL OR status IN ('ok', 'degraded', 'failing', 'disabled')",
            name="ck_sources_status",
        ),
        sa.CheckConstraint("poll_interval_minutes > 0", name="ck_sources_poll_interval_positive"),
        sa.CheckConstraint("consecutive_failures >= 0", name="ck_sources_failures_non_negative"),
    )
    op.create_index("ix_sources_company_id", "sources", ["company_id"])

    op.create_table(
        "announcements",
        _id(),
        sa.Column(
            "company_id",
            sa.BigInteger(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.BigInteger(),
            sa.ForeignKey("sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("kind", sa.Text(), nullable=False, server_default=sa.text("'other'")),
        _tstz("published_at"),
        sa.Column("published_precision", sa.Text()),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB()),
        _tstz("first_seen_at", nullable=False, server_default=sa.func.now()),
        _tstz("updated_at", nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("original_url", name="uq_announcements_original_url"),
        sa.CheckConstraint(
            "kind IN ('model_release', 'update', 'deprecation', 'research', 'other')",
            name="ck_announcements_kind",
        ),
        sa.CheckConstraint(
            "published_precision IS NULL OR published_precision IN ('day', 'datetime')",
            name="ck_announcements_published_precision",
        ),
        sa.CheckConstraint(
            "(published_at IS NULL) = (published_precision IS NULL)",
            name="ck_announcements_published_pair",
        ),
    )
    op.execute(
        "CREATE INDEX ix_announcements_published_at ON announcements (published_at DESC NULLS LAST)"
    )
    op.execute(
        "CREATE INDEX ix_announcements_company_published "
        "ON announcements (company_id, published_at DESC NULLS LAST)"
    )
    op.create_index("ix_announcements_source_id", "announcements", ["source_id"])
    op.create_index("ix_announcements_kind", "announcements", ["kind"])
    op.execute(
        "CREATE INDEX ix_announcements_fts ON announcements "
        "USING gin (to_tsvector('english', title || ' ' || coalesce(description, '')))"
    )

    op.create_table(
        "announcement_categories",
        sa.Column(
            "announcement_id",
            sa.BigInteger(),
            sa.ForeignKey("announcements.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "category_id",
            sa.BigInteger(),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_announcement_categories_category_id", "announcement_categories", ["category_id"]
    )

    op.create_table(
        "models",
        _id(),
        sa.Column(
            "company_id",
            sa.BigInteger(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("family_name", sa.Text(), nullable=False),
        sa.UniqueConstraint("company_id", "slug", name="uq_models_company_id_slug"),
    )

    op.create_table(
        "model_versions",
        _id(),
        sa.Column(
            "model_id",
            sa.BigInteger(),
            sa.ForeignKey("models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_label", sa.Text()),
        sa.Column("display_name", sa.Text(), nullable=False),
        _tstz("first_announced_at"),
        sa.Column("first_announced_precision", sa.Text()),
        sa.Column(
            "first_announcement_id",
            sa.BigInteger(),
            sa.ForeignKey("announcements.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint("model_id", "display_name", name="uq_model_versions_model_id_display_name"),
        sa.CheckConstraint(
            "first_announced_precision IS NULL OR first_announced_precision IN ('day', 'datetime')",
            name="ck_model_versions_first_announced_precision",
        ),
        sa.CheckConstraint(
            "(first_announced_at IS NULL) = (first_announced_precision IS NULL)",
            name="ck_model_versions_first_announced_pair",
        ),
    )
    op.create_index("ix_model_versions_model_id", "model_versions", ["model_id"])
    op.create_index(
        "ix_model_versions_first_announcement_id", "model_versions", ["first_announcement_id"]
    )
    op.execute(
        "CREATE INDEX ix_model_versions_display_name_trgm "
        "ON model_versions USING gin (display_name gin_trgm_ops)"
    )

    op.create_table(
        "model_version_categories",
        sa.Column(
            "model_version_id",
            sa.BigInteger(),
            sa.ForeignKey("model_versions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "category_id",
            sa.BigInteger(),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_model_version_categories_category_id", "model_version_categories", ["category_id"]
    )

    op.create_table(
        "announcement_models",
        sa.Column(
            "announcement_id",
            sa.BigInteger(),
            sa.ForeignKey("announcements.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "model_version_id",
            sa.BigInteger(),
            sa.ForeignKey("model_versions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("matched_text", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_announcement_models_model_version_id", "announcement_models", ["model_version_id"]
    )

    op.create_table(
        "sync_runs",
        _id(),
        sa.Column(
            "source_id",
            sa.BigInteger(),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _tstz("started_at", nullable=False, server_default=sa.func.now()),
        _tstz("finished_at"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("items_found", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_new", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_filtered", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("http_status", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'failed')", name="ck_sync_runs_status"
        ),
        sa.CheckConstraint(
            "items_found >= 0 AND items_new >= 0 AND items_filtered >= 0",
            name="ck_sync_runs_counts_non_negative",
        ),
    )
    op.execute("CREATE INDEX ix_sync_runs_source_started ON sync_runs (source_id, started_at DESC)")

    _apply_role_grants()


def _apply_role_grants() -> None:
    """Explicit least-privilege grants, independent of the Docker init script.

    - modelradar_worker: read/write on application tables (the only writer).
    - modelradar_api: read-only on application tables.
    - Neither role may touch alembic_version.
    Roles are skipped if they do not exist (e.g. a bare database).
    """
    tables = ", ".join(TABLES)
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'modelradar_worker') THEN
            GRANT USAGE ON SCHEMA public TO modelradar_worker;
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {tables} TO modelradar_worker;
            REVOKE ALL ON TABLE alembic_version FROM modelradar_worker;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'modelradar_api') THEN
            GRANT USAGE ON SCHEMA public TO modelradar_api;
            GRANT SELECT ON TABLE {tables} TO modelradar_api;
            REVOKE ALL ON TABLE alembic_version FROM modelradar_api;
          END IF;
        END
        $$;
        """  # noqa: S608 - table names are constants defined above
    )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
