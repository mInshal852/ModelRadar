"""Idempotent synchronisation of config/ into the database.

Rules:
- Config-owned fields (names, URLs, verification metadata, relevance rules, ...) are updated.
- Runtime fields (etag, last_modified, last_synced_at, last_error, consecutive_failures, and
  the status of enabled sources) are never overwritten.
- Nothing is ever deleted. Rows that no longer appear in the config are only reported.
- No announcements are created: this module touches categories, companies,
  company_categories and sources only.

Sources are identified by (company, URL). The `slug` in YAML identifies a source inside the
configuration; the database schema has no source slug column (approved schema, unchanged).
"""

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from worker.sources.loader import LoadedConfig
from worker.sources.schema import CompanyConfig, SourceConfig


@dataclass
class EntityCounts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0

    def record(self, outcome: str) -> None:
        setattr(self, outcome, getattr(self, outcome) + 1)


@dataclass
class SyncSummary:
    categories: EntityCounts = field(default_factory=EntityCounts)
    companies: EntityCounts = field(default_factory=EntityCounts)
    sources: EntityCounts = field(default_factory=EntityCounts)
    company_category_links_added: int = 0
    warnings: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [
            f"categories: {self.categories}",
            f"companies:  {self.companies}",
            f"sources:    {self.sources}",
            f"company_categories links added: {self.company_category_links_added}",
        ]
        out += [f"WARNING: {w}" for w in self.warnings]
        return out


def _json(value: Any) -> Any:
    """asyncpg returns JSONB as text; normalise to Python for comparison."""
    return json.loads(value) if isinstance(value, str) else value


def _dump(model: Any) -> str | None:
    return None if model is None else json.dumps(model, sort_keys=True)


async def _upsert(
    conn: AsyncConnection,
    *,
    table: str,
    key: dict[str, Any],
    values: dict[str, Any],
    json_columns: frozenset[str] = frozenset(),
    computed_update: dict[str, Any] | None = None,
) -> tuple[int, str]:
    """Insert or update one row. Returns (id, 'created' | 'updated' | 'unchanged').

    `values` are config-owned columns. `computed_update` holds extra columns that are written
    on update only if they differ (used for status transitions).
    """
    cols = list(key) + list(values)
    where = " AND ".join(f"{k} = :k_{k}" for k in key)
    select_cols = ", ".join(["id", *values, *(computed_update or {})])
    existing = (
        (
            await conn.execute(
                text(f"SELECT {select_cols} FROM {table} WHERE {where}"),  # noqa: S608
                {f"k_{k}": v for k, v in key.items()},
            )
        )
        .mappings()
        .first()
    )

    def placeholder(col: str) -> str:
        return f"CAST(:{col} AS jsonb)" if col in json_columns else f":{col}"

    params = {**key, **{c: (_dump(v) if c in json_columns else v) for c, v in values.items()}}

    if existing is None:
        initial = {**params, **(computed_update or {})}
        insert_cols = cols + list(computed_update or {})
        row = (
            await conn.execute(
                text(
                    f"INSERT INTO {table} ({', '.join(insert_cols)}) "  # noqa: S608
                    f"VALUES ({', '.join(placeholder(c) for c in insert_cols)}) RETURNING id"
                ),
                initial,
            )
        ).one()
        return int(row[0]), "created"

    row_id = int(existing["id"])
    changed: dict[str, Any] = {}
    for col, wanted in values.items():
        current = existing[col]
        if col in json_columns:
            if _json(current) != _json(_dump(wanted)):
                changed[col] = wanted
        elif current != wanted:
            changed[col] = wanted
    for col, wanted in (computed_update or {}).items():
        if existing[col] != wanted:
            changed[col] = wanted
    if not changed:
        return row_id, "unchanged"

    assignments = ", ".join(f"{c} = {placeholder(c)}" for c in changed)
    await conn.execute(
        text(f"UPDATE {table} SET {assignments} WHERE id = :row_id"),  # noqa: S608
        {
            **{c: (_dump(v) if c in json_columns else v) for c, v in changed.items()},
            "row_id": row_id,
        },
    )
    return row_id, "updated"


async def _sync_categories(
    conn: AsyncConnection, config: LoadedConfig, out: SyncSummary
) -> dict[str, int]:
    ids: dict[str, int] = {}
    for order, node in enumerate(config.categories):
        parent_id, outcome = await _upsert(
            conn,
            table="categories",
            key={"slug": node.slug},
            values={"name": node.name, "parent_id": None, "sort_order": order},
        )
        out.categories.record(outcome)
        ids[node.slug] = parent_id
        for child_order, child in enumerate(node.children):
            child_id, outcome = await _upsert(
                conn,
                table="categories",
                key={"slug": child.slug},
                values={"name": child.name, "parent_id": parent_id, "sort_order": child_order},
            )
            out.categories.record(outcome)
            ids[child.slug] = child_id
    return ids


def _source_values(source: SourceConfig) -> dict[str, Any]:
    verified_at = (
        dt.datetime.combine(source.verified_at, dt.time.min, tzinfo=dt.UTC)
        if source.verified_at
        else None
    )
    notes = source.verification_notes
    if not source.enabled:
        notes = f"DISABLED: {source.disabled_reason}\n{notes}"
    return {
        "name": source.name,
        "kind": source.kind,
        "hosting": source.hosting,
        "hosting_notes": source.hosting_notes,
        "content_scope": source.content_scope,
        "verification_level": source.verification_level,
        "verified_at": verified_at,
        "verification_notes": notes,
        "relevance_rules": (
            source.relevance_rules.model_dump()
            if source.relevance_rules and not source.relevance_rules.is_empty()
            else None
        ),
        "extractor_config": source.extractor_config,
        "poll_interval_minutes": source.poll_interval_minutes,
    }


async def _sync_source(
    conn: AsyncConnection, company_id: int, source: SourceConfig, out: SyncSummary
) -> int:
    values = _source_values(source)
    existing_status = (
        await conn.execute(
            text("SELECT status FROM sources WHERE company_id = :c AND url = :u"),
            {"c": company_id, "u": source.url},
        )
    ).scalar_one_or_none()

    # Status: disabled sources are 'disabled'. Enabled sources keep their runtime status;
    # a newly enabled (previously disabled) or new source starts as NULL (never synced).
    if not source.enabled:
        wanted_status: str | None = "disabled"
    elif existing_status in (None, "disabled"):
        wanted_status = None
    else:
        wanted_status = existing_status

    source_id, outcome = await _upsert(
        conn,
        table="sources",
        key={"company_id": company_id, "url": source.url},
        values=values,
        json_columns=frozenset({"relevance_rules", "extractor_config"}),
        computed_update={"status": wanted_status},
    )
    out.sources.record(outcome)
    return source_id


async def _sync_company(
    conn: AsyncConnection,
    company: CompanyConfig,
    category_ids: dict[str, int],
    out: SyncSummary,
) -> None:
    company_id, outcome = await _upsert(
        conn,
        table="companies",
        key={"slug": company.slug},
        values={
            "name": company.name,
            "website_url": company.website_url,
            "country": company.country,
            "description": company.description,
        },
    )
    out.companies.record(outcome)

    wanted = {category_ids[slug] for slug in company.categories}
    current = {
        int(r[0])
        for r in await conn.execute(
            text("SELECT category_id FROM company_categories WHERE company_id = :c"),
            {"c": company_id},
        )
    }
    for category_id in sorted(wanted - current):
        await conn.execute(
            text("INSERT INTO company_categories (company_id, category_id) VALUES (:c, :k)"),
            {"c": company_id, "k": category_id},
        )
        out.company_category_links_added += 1
    if current - wanted:
        out.warnings.append(
            f"{company.slug}: {len(current - wanted)} category link(s) in the database are no "
            "longer in the config (not deleted)"
        )

    for source in company.sources:
        await _sync_source(conn, company_id, source, out)

    configured_urls = [s.url for s in company.sources]
    orphans = (
        await conn.execute(
            text("SELECT url FROM sources WHERE company_id = :c AND NOT (url = ANY(:urls))"),
            {"c": company_id, "urls": configured_urls},
        )
    ).all()
    for (url,) in orphans:
        out.warnings.append(
            f"{company.slug}: source {url} is in the database but not in the config (kept)"
        )


async def sync_config(conn: AsyncConnection, config: LoadedConfig) -> SyncSummary:
    """Synchronise config into the database using `conn` (caller owns the transaction)."""
    summary = SyncSummary()
    category_ids = await _sync_categories(conn, config, summary)
    for company in config.companies:
        await _sync_company(conn, company, category_ids, summary)

    config_slugs = [c.slug for c in config.companies]
    extra = (
        await conn.execute(
            text("SELECT slug FROM companies WHERE NOT (slug = ANY(:slugs))"),
            {"slugs": config_slugs},
        )
    ).all()
    for (slug,) in extra:
        summary.warnings.append(f"company '{slug}' is in the database but not in the config (kept)")
    return summary
