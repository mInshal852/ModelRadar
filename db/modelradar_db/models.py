"""ModelRadar database schema (public announcement data only).

This metadata is the source of truth the migrations are checked against. There are
deliberately no user, session, account or tracking tables.

Conventions:
- Unknown values are NULL; nothing is defaulted to an invented value.
- Enumerations are TEXT columns with CHECK constraints (easy to evolve in migrations).
- `published_at` is the original publication date from the source and may be NULL.
  `first_seen_at` is when ModelRadar discovered the item and is stored separately.
"""

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SOURCE_KINDS = ("rss", "atom", "github", "api", "sitemap", "html", "manual")
SOURCE_HOSTING = ("first_party", "official_third_party")
SOURCE_CONTENT_SCOPES = ("dedicated_ai", "mixed")
SOURCE_VERIFICATION_LEVELS = ("http_only", "content_sampled", "content_verified")
SOURCE_STATUSES = ("ok", "degraded", "failing", "disabled")
ANNOUNCEMENT_KINDS = ("model_release", "update", "deprecation", "research", "other")
DATE_PRECISIONS = ("day", "datetime")
SYNC_RUN_STATUSES = ("running", "success", "failed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


def _id() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(always=False), primary_key=True)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_categories_slug"),
        CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name="ck_categories_not_own_parent"
        ),
        Index("ix_categories_parent_id", "parent_id"),
    )

    id: Mapped[int] = _id()
    slug: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("slug", name="uq_companies_slug"),)

    id: Mapped[int] = _id()
    slug: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    website_url: Mapped[str] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


class CompanyCategory(Base):
    __tablename__ = "company_categories"
    __table_args__ = (Index("ix_company_categories_category_id", "category_id"),)

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True
    )


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("company_id", "url", name="uq_sources_company_id_url"),
        CheckConstraint(_in("kind", SOURCE_KINDS), name="ck_sources_kind"),
        CheckConstraint(_in("hosting", SOURCE_HOSTING), name="ck_sources_hosting"),
        CheckConstraint(
            _in("content_scope", SOURCE_CONTENT_SCOPES), name="ck_sources_content_scope"
        ),
        CheckConstraint(
            _in("verification_level", SOURCE_VERIFICATION_LEVELS),
            name="ck_sources_verification_level",
        ),
        CheckConstraint(
            "status IS NULL OR " + _in("status", SOURCE_STATUSES), name="ck_sources_status"
        ),
        CheckConstraint("poll_interval_minutes > 0", name="ck_sources_poll_interval_positive"),
        CheckConstraint("consecutive_failures >= 0", name="ck_sources_failures_non_negative"),
        Index("ix_sources_company_id", "company_id"),
    )

    id: Mapped[int] = _id()
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    hosting: Mapped[str] = mapped_column(Text)
    hosting_notes: Mapped[str | None] = mapped_column(Text)
    content_scope: Mapped[str] = mapped_column(Text)
    verification_level: Mapped[str] = mapped_column(Text, server_default=text("'http_only'"))
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    verification_notes: Mapped[str | None] = mapped_column(Text)
    relevance_rules: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    extractor_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    poll_interval_minutes: Mapped[int] = mapped_column(Integer)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # NULL means the source has never been synced (status unknown).
    status: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (
        UniqueConstraint("original_url", name="uq_announcements_original_url"),
        CheckConstraint(_in("kind", ANNOUNCEMENT_KINDS), name="ck_announcements_kind"),
        CheckConstraint(
            "published_precision IS NULL OR " + _in("published_precision", DATE_PRECISIONS),
            name="ck_announcements_published_precision",
        ),
        # A precision only makes sense together with a date, and vice versa.
        CheckConstraint(
            "(published_at IS NULL) = (published_precision IS NULL)",
            name="ck_announcements_published_pair",
        ),
        Index("ix_announcements_published_at", text("published_at DESC NULLS LAST")),
        Index(
            "ix_announcements_company_published", "company_id", text("published_at DESC NULLS LAST")
        ),
        Index("ix_announcements_source_id", "source_id"),
        Index("ix_announcements_kind", "kind"),
        Index(
            "ix_announcements_fts",
            text("to_tsvector('english', title || ' ' || coalesce(description, ''))"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[int] = _id()
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(Text)  # exactly as published
    description: Mapped[str | None] = mapped_column(Text)  # source text/excerpt only
    kind: Mapped[str] = mapped_column(Text, server_default=text("'other'"))
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    published_precision: Mapped[str | None] = mapped_column(Text)
    original_url: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnnouncementCategory(Base):
    __tablename__ = "announcement_categories"
    __table_args__ = (Index("ix_announcement_categories_category_id", "category_id"),)

    announcement_id: Mapped[int] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True
    )


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("company_id", "slug", name="uq_models_company_id_slug"),)

    id: Mapped[int] = _id()
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    slug: Mapped[str] = mapped_column(Text)
    family_name: Mapped[str] = mapped_column(Text)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint(
            "model_id", "display_name", name="uq_model_versions_model_id_display_name"
        ),
        CheckConstraint(
            "first_announced_precision IS NULL OR "
            + _in("first_announced_precision", DATE_PRECISIONS),
            name="ck_model_versions_first_announced_precision",
        ),
        CheckConstraint(
            "(first_announced_at IS NULL) = (first_announced_precision IS NULL)",
            name="ck_model_versions_first_announced_pair",
        ),
        Index("ix_model_versions_model_id", "model_id"),
        Index("ix_model_versions_first_announcement_id", "first_announcement_id"),
        Index(
            "ix_model_versions_display_name_trgm",
            "display_name",
            postgresql_using="gin",
            postgresql_ops={"display_name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = _id()
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"))
    version_label: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    # Date of the earliest official announcement; not necessarily general availability.
    first_announced_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    first_announced_precision: Mapped[str | None] = mapped_column(Text)
    # Provenance: every model version traces to an official announcement.
    first_announcement_id: Mapped[int] = mapped_column(
        ForeignKey("announcements.id", ondelete="RESTRICT")
    )


class ModelVersionCategory(Base):
    __tablename__ = "model_version_categories"
    __table_args__ = (Index("ix_model_version_categories_category_id", "category_id"),)

    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True
    )


class AnnouncementModel(Base):
    __tablename__ = "announcement_models"
    __table_args__ = (Index("ix_announcement_models_model_version_id", "model_version_id"),)

    announcement_id: Mapped[int] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), primary_key=True
    )
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), primary_key=True
    )
    matched_text: Mapped[str] = mapped_column(Text)  # the literal text that matched


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint(_in("status", SYNC_RUN_STATUSES), name="ck_sync_runs_status"),
        CheckConstraint(
            "items_found >= 0 AND items_new >= 0 AND items_filtered >= 0",
            name="ck_sync_runs_counts_non_negative",
        ),
        Index("ix_sync_runs_source_started", "source_id", text("started_at DESC")),
    )

    id: Mapped[int] = _id()
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text)
    items_found: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    items_new: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    items_filtered: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    http_status: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)


EXPECTED_TABLES = frozenset(Base.metadata.tables)
