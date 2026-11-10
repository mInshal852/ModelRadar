"""Persist parsed feed entries as announcements (insert, update on change, never delete)."""

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from worker.ingest.entries import ParsedEntry, announcement_url_key


@dataclass
class StoreResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    conflicts: int = 0  # URL already stored by another source / concurrent writer


def _meta(entry: ParsedEntry) -> str | None:
    return None if entry.metadata is None else json.dumps(entry.metadata, sort_keys=True)


async def store_entries(
    conn: AsyncConnection, company_id: int, source_id: int, entries: list[ParsedEntry]
) -> StoreResult:
    """Store entries inside the caller's transaction.

    - original_url is the duplicate-prevention key (unique constraint). URLs that differ only
      by case of host or trailing slash are recognised as the same announcement; the stored
      original_url is never rewritten.
    - On a content change (content_hash) title, description and metadata are updated.
      published_at, published_precision, first_seen_at, kind, company and source are kept.
      A publication date is only filled in when the stored one is NULL.
    """
    result = StoreResult()
    if not entries:
        return result

    urls = [e.url for e in entries]
    rows = (
        await conn.execute(
            text(
                "SELECT id, original_url, content_hash FROM announcements "
                "WHERE source_id = :s OR original_url = ANY(:urls)"
            ),
            {"s": source_id, "urls": urls},
        )
    ).all()
    by_key: dict[str, Any] = {announcement_url_key(r.original_url): r for r in rows}

    for entry in entries:
        existing = by_key.get(announcement_url_key(entry.url))
        if existing is None:
            row = (
                await conn.execute(
                    text(
                        "INSERT INTO announcements (company_id, source_id, title, description, "
                        "published_at, published_precision, original_url, content_hash, metadata) "
                        "VALUES (:company, :source, :title, :description, :published_at, "
                        ":precision, :url, :hash, CAST(:metadata AS jsonb)) "
                        "ON CONFLICT (original_url) DO NOTHING RETURNING id"
                    ),
                    {
                        "company": company_id,
                        "source": source_id,
                        "title": entry.title,
                        "description": entry.description,
                        "published_at": entry.published_at,
                        "precision": entry.published_precision,
                        "url": entry.url,
                        "hash": entry.content_hash,
                        "metadata": _meta(entry),
                    },
                )
            ).first()
            if row is None:
                result.conflicts += 1
            else:
                result.inserted += 1
            continue

        if existing.content_hash == entry.content_hash:
            # Same content; still fill a previously unknown publication date if the feed has one.
            if entry.published_at is not None:
                filled = await _fill_date(conn, existing.id, entry)
                result.updated += 1 if filled else 0
                result.unchanged += 0 if filled else 1
            else:
                result.unchanged += 1
            continue

        await conn.execute(
            text(
                "UPDATE announcements SET title = :title, description = :description, "
                "content_hash = :hash, metadata = CAST(:metadata AS jsonb), updated_at = now(), "
                "published_at = CASE WHEN published_at IS NULL THEN :published_at "
                "ELSE published_at END, "
                "published_precision = CASE WHEN published_at IS NULL THEN :precision "
                "ELSE published_precision END WHERE id = :id"
            ),
            {
                "id": existing.id,
                "title": entry.title,
                "description": entry.description,
                "hash": entry.content_hash,
                "metadata": _meta(entry),
                "published_at": entry.published_at,
                "precision": entry.published_precision,
            },
        )
        result.updated += 1
    return result


async def _fill_date(conn: AsyncConnection, announcement_id: int, entry: ParsedEntry) -> bool:
    row = (
        await conn.execute(
            text(
                "UPDATE announcements SET published_at = :p, published_precision = :prec, "
                "updated_at = now() WHERE id = :id AND published_at IS NULL RETURNING id"
            ),
            {"id": announcement_id, "p": entry.published_at, "prec": entry.published_precision},
        )
    ).first()
    return row is not None
