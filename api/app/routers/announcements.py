import datetime as dt
from collections import defaultdict
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db import get_connection
from app.schemas import Announcement, AnnouncementKind, CategoryRef, CompanyRef, Page
from app.sqlutil import PageNumber, PageSize, SearchText, Slug, like_pattern, page_count

router = APIRouter(prefix="/v1/announcements", tags=["announcements"])

FTS = "to_tsvector('english', a.title || ' ' || coalesce(a.description, ''))"

# An announcement's categories are its own (announcement_categories) when it has any,
# otherwise the categories of the company that published it (the approved inheritance rule).
CATEGORY_FILTER = """
EXISTS (
  SELECT 1 FROM categories k
  WHERE (k.slug = :category
         OR k.parent_id = (SELECT id FROM categories WHERE slug = :category))
    AND (
      EXISTS (SELECT 1 FROM announcement_categories ac
              WHERE ac.announcement_id = a.id AND ac.category_id = k.id)
      OR (NOT EXISTS (SELECT 1 FROM announcement_categories ac2
                      WHERE ac2.announcement_id = a.id)
          AND EXISTS (SELECT 1 FROM company_categories cc
                      WHERE cc.company_id = a.company_id AND cc.category_id = k.id))
    )
)
"""


@router.get("", response_model=Page[Announcement])
async def list_announcements(
    conn: Annotated[AsyncConnection, Depends(get_connection)],
    q: SearchText | None = None,
    category: Slug | None = None,
    company: Slug | None = None,
    kind: AnnouncementKind | None = None,
    published_from: Annotated[dt.date | None, Query()] = None,
    published_to: Annotated[dt.date | None, Query()] = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> Page[Announcement]:
    """Announcements, newest publication date first; undated ones last.

    Sorting never uses the discovery time. A date range excludes undated announcements.
    """
    if published_from and published_to and published_from > published_to:
        raise HTTPException(status_code=422, detail="published_from must not be after published_to")

    where: list[str] = []
    params: dict[str, object] = {}
    if q:
        term = q.strip()
        where.append(
            f"({FTS} @@ websearch_to_tsquery('english', :q) OR a.title ILIKE :like ESCAPE '\\')"
        )
        params.update(q=term, like=like_pattern(term))
    if company:
        where.append("c.slug = :company")
        params["company"] = company
    if kind:
        where.append("a.kind = :kind")
        params["kind"] = kind
    if category:
        where.append(CATEGORY_FILTER)
        params["category"] = category
    if published_from:
        where.append("a.published_at >= :pfrom")
        params["pfrom"] = dt.datetime.combine(published_from, dt.time.min, tzinfo=dt.UTC)
    if published_to:
        where.append("a.published_at < :pto")
        params["pto"] = dt.datetime.combine(
            published_to + dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC
        )
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    base = (
        "FROM announcements a JOIN companies c ON c.id = a.company_id "
        "JOIN sources s ON s.id = a.source_id " + where_sql
    )
    total = int((await conn.execute(text(f"SELECT count(*) {base}"), params)).scalar_one())  # noqa: S608

    rows = (
        (
            await conn.execute(
                text(
                    "SELECT a.id, a.title, a.description, a.kind, a.published_at, "  # noqa: S608
                    "a.published_precision, a.original_url, c.slug AS company_slug, "
                    f"c.name AS company_name, s.name AS source_name {base} "
                    "ORDER BY a.published_at DESC NULLS LAST, a.id DESC LIMIT :limit OFFSET :offset"
                ),
                {**params, "limit": page_size, "offset": (page - 1) * page_size},
            )
        )
        .mappings()
        .all()
    )
    ids = [r["id"] for r in rows]
    categories = await _categories_for(conn, ids)
    models = await _models_for(conn, ids)

    items = [
        Announcement(
            id=r["id"],
            title=r["title"],
            description=r["description"],
            kind=r["kind"],
            published_at=r["published_at"],
            published_precision=r["published_precision"],
            original_url=r["original_url"],
            source_domain=(urlparse(r["original_url"]).hostname or "").lower(),
            source_name=r["source_name"],
            company=CompanyRef(slug=r["company_slug"], name=r["company_name"]),
            categories=categories.get(r["id"], []),
            models=models.get(r["id"], []),
        )
        for r in rows
    ]
    return Page[Announcement](
        items=items, total=total, page=page, page_size=page_size, pages=page_count(total, page_size)
    )


async def _categories_for(conn: AsyncConnection, ids: list[int]) -> dict[int, list[CategoryRef]]:
    if not ids:
        return {}
    out: dict[int, list[CategoryRef]] = defaultdict(list)
    own = await conn.execute(
        text(
            "SELECT ac.announcement_id AS aid, k.slug, k.name FROM announcement_categories ac "
            "JOIN categories k ON k.id = ac.category_id WHERE ac.announcement_id = ANY(:ids) "
            "ORDER BY k.sort_order, k.id"
        ),
        {"ids": ids},
    )
    for r in own.mappings():
        out[r["aid"]].append(CategoryRef(slug=r["slug"], name=r["name"]))
    # Fall back to company categories only for announcements without their own.
    own_ids = set(out)
    result: dict[int, list[CategoryRef]] = dict(out)
    inherited_rows = await conn.execute(
        text(
            "SELECT a.id AS aid, k.slug, k.name FROM announcements a "
            "JOIN company_categories cc ON cc.company_id = a.company_id "
            "JOIN categories k ON k.id = cc.category_id WHERE a.id = ANY(:ids) "
            "ORDER BY k.sort_order, k.id"
        ),
        {"ids": [i for i in ids if i not in own_ids]},
    )
    for r in inherited_rows.mappings():
        result.setdefault(r["aid"], []).append(CategoryRef(slug=r["slug"], name=r["name"]))
    return result


async def _models_for(conn: AsyncConnection, ids: list[int]) -> dict[int, list[str]]:
    if not ids:
        return {}
    out: dict[int, list[str]] = defaultdict(list)
    result = await conn.execute(
        text(
            "SELECT am.announcement_id AS aid, mv.display_name FROM announcement_models am "
            "JOIN model_versions mv ON mv.id = am.model_version_id "
            "WHERE am.announcement_id = ANY(:ids) ORDER BY mv.display_name"
        ),
        {"ids": ids},
    )
    for r in result.mappings():
        out[r["aid"]].append(r["display_name"])
    return out
