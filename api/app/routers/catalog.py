"""Categories, companies, models, sources and meta (all read-only)."""

from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db import get_connection
from app.schemas import (
    Category,
    CategoryRef,
    Company,
    CompanyRef,
    Meta,
    ModelFamily,
    ModelVersion,
    Page,
    Source,
    SourceRun,
)
from app.sqlutil import PageNumber, PageSize, SearchText, Slug, like_pattern, page_count

router = APIRouter(prefix="/v1", tags=["catalog"])

# Counts use the same inheritance rule as the announcement filter: an announcement's own
# categories, or its company's categories when it has none.
EFFECTIVE_CATEGORIES = """
WITH effective AS (
  SELECT announcement_id, category_id FROM announcement_categories
  UNION ALL
  SELECT a.id, cc.category_id FROM announcements a
  JOIN company_categories cc ON cc.company_id = a.company_id
  WHERE NOT EXISTS (SELECT 1 FROM announcement_categories ac WHERE ac.announcement_id = a.id)
)
"""

CATEGORY_MATCH = """
(k.slug = :category OR k.parent_id = (SELECT id FROM categories WHERE slug = :category))
"""


@router.get("/categories", response_model=list[Category])
async def list_categories(
    conn: Annotated[AsyncConnection, Depends(get_connection)],
) -> list[Category]:
    """The category tree with announcement and company counts computed from real records."""
    rows = (
        (
            await conn.execute(
                text(
                    EFFECTIVE_CATEGORIES
                    + """
SELECT k.id, k.slug, k.name, k.description, k.parent_id,
  (SELECT count(DISTINCT e.announcement_id) FROM effective e
    WHERE e.category_id = k.id
       OR e.category_id IN (SELECT ch.id FROM categories ch WHERE ch.parent_id = k.id)
  ) AS announcement_count,
  (SELECT count(DISTINCT cc.company_id) FROM company_categories cc
    WHERE cc.category_id = k.id
       OR cc.category_id IN (SELECT ch.id FROM categories ch WHERE ch.parent_id = k.id)
  ) AS company_count
FROM categories k ORDER BY k.parent_id NULLS FIRST, k.sort_order, k.id
"""
                )
            )
        )
        .mappings()
        .all()
    )
    nodes = {
        r["id"]: Category(
            slug=r["slug"],
            name=r["name"],
            description=r["description"],
            announcement_count=r["announcement_count"],
            company_count=r["company_count"],
            children=[],
        )
        for r in rows
    }
    roots: list[Category] = []
    for r in rows:
        if r["parent_id"] is None:
            roots.append(nodes[r["id"]])
        else:
            nodes[r["parent_id"]].children.append(nodes[r["id"]])
    return roots


async def _company_categories(
    conn: AsyncConnection, company_ids: list[int]
) -> dict[int, list[CategoryRef]]:
    out: dict[int, list[CategoryRef]] = defaultdict(list)
    if not company_ids:
        return out
    result = await conn.execute(
        text(
            "SELECT cc.company_id AS cid, k.slug, k.name FROM company_categories cc "
            "JOIN categories k ON k.id = cc.category_id WHERE cc.company_id = ANY(:ids) "
            "ORDER BY k.parent_id NULLS FIRST, k.sort_order, k.id"
        ),
        {"ids": company_ids},
    )
    for r in result.mappings():
        out[r["cid"]].append(CategoryRef(slug=r["slug"], name=r["name"]))
    return out


@router.get("/companies", response_model=Page[Company])
async def list_companies(
    conn: Annotated[AsyncConnection, Depends(get_connection)],
    q: SearchText | None = None,
    category: Slug | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 50,
) -> Page[Company]:
    where: list[str] = []
    params: dict[str, object] = {}
    if q:
        where.append("c.name ILIKE :like ESCAPE '\\'")
        params["like"] = like_pattern(q.strip())
    if category:
        where.append(
            "EXISTS (SELECT 1 FROM company_categories cc JOIN categories k ON k.id = cc.category_id "
            f"WHERE cc.company_id = c.id AND {CATEGORY_MATCH})"
        )
        params["category"] = category
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = int(
        (
            await conn.execute(text(f"SELECT count(*) FROM companies c {where_sql}"), params)
        ).scalar_one()  # noqa: S608
    )
    rows = (
        (
            await conn.execute(
                text(
                    "SELECT c.id, c.slug, c.name, c.website_url, c.country, c.description, "  # noqa: S608
                    "(SELECT count(*) FROM announcements a WHERE a.company_id = c.id) AS announcement_count, "
                    "(SELECT count(*) FROM sources s WHERE s.company_id = c.id) AS source_count, "
                    "(SELECT max(a.published_at) FROM announcements a WHERE a.company_id = c.id) "
                    f"AS latest_published_at FROM companies c {where_sql} "
                    "ORDER BY lower(c.name), c.id LIMIT :limit OFFSET :offset"
                ),
                {**params, "limit": page_size, "offset": (page - 1) * page_size},
            )
        )
        .mappings()
        .all()
    )
    categories = await _company_categories(conn, [r["id"] for r in rows])
    items = [
        Company(
            slug=r["slug"],
            name=r["name"],
            website_url=r["website_url"],
            country=r["country"],
            description=r["description"],
            categories=categories.get(r["id"], []),
            announcement_count=r["announcement_count"],
            source_count=r["source_count"],
            latest_published_at=r["latest_published_at"],
        )
        for r in rows
    ]
    return Page[Company](
        items=items, total=total, page=page, page_size=page_size, pages=page_count(total, page_size)
    )


@router.get("/companies/{slug}", response_model=Company)
async def get_company(
    slug: str, conn: Annotated[AsyncConnection, Depends(get_connection)]
) -> Company:
    result = await list_companies(conn, q=None, category=None, page=1, page_size=100)
    for company in result.items:
        if company.slug == slug:
            return company
    raise HTTPException(status_code=404, detail="Company not found")


@router.get("/models", response_model=Page[ModelFamily])
async def list_models(
    conn: Annotated[AsyncConnection, Depends(get_connection)],
    q: SearchText | None = None,
    company: Slug | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 50,
) -> Page[ModelFamily]:
    """Model families and versions detected from official announcements (not exhaustive)."""
    where: list[str] = []
    params: dict[str, object] = {}
    if q:
        where.append(
            "(m.family_name ILIKE :like ESCAPE '\\' OR EXISTS (SELECT 1 FROM model_versions v "
            "WHERE v.model_id = m.id AND v.display_name ILIKE :like ESCAPE '\\'))"
        )
        params["like"] = like_pattern(q.strip())
    if company:
        where.append("c.slug = :company")
        params["company"] = company
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    base = f"FROM models m JOIN companies c ON c.id = m.company_id {where_sql}"

    total = int((await conn.execute(text(f"SELECT count(*) {base}"), params)).scalar_one())  # noqa: S608
    families = (
        (
            await conn.execute(
                text(
                    "SELECT m.id, m.slug, m.family_name, c.slug AS company_slug, "  # noqa: S608
                    f"c.name AS company_name {base} "
                    "ORDER BY lower(m.family_name), m.id LIMIT :limit OFFSET :offset"
                ),
                {**params, "limit": page_size, "offset": (page - 1) * page_size},
            )
        )
        .mappings()
        .all()
    )
    ids = [f["id"] for f in families]
    versions: dict[int, list[ModelVersion]] = defaultdict(list)
    if ids:
        version_rows = (
            (
                await conn.execute(
                    text(
                        "SELECT v.id, v.model_id, v.display_name, v.version_label, "
                        "v.first_announced_at, v.first_announced_precision, "
                        "a.title AS announcement_title, a.original_url AS announcement_url "
                        "FROM model_versions v JOIN announcements a ON a.id = v.first_announcement_id "
                        "WHERE v.model_id = ANY(:ids) "
                        "ORDER BY v.first_announced_at DESC NULLS LAST, v.id DESC"
                    ),
                    {"ids": ids},
                )
            )
            .mappings()
            .all()
        )
        cat_rows = await conn.execute(
            text(
                "SELECT vc.model_version_id AS vid, k.slug, k.name FROM model_version_categories vc "
                "JOIN categories k ON k.id = vc.category_id "
                "WHERE vc.model_version_id = ANY(:vids) ORDER BY k.sort_order, k.id"
            ),
            {"vids": [v["id"] for v in version_rows]},
        )
        by_version: dict[int, list[CategoryRef]] = defaultdict(list)
        for r in cat_rows.mappings():
            by_version[r["vid"]].append(CategoryRef(slug=r["slug"], name=r["name"]))
        for v in version_rows:
            versions[v["model_id"]].append(
                ModelVersion(
                    display_name=v["display_name"],
                    version_label=v["version_label"],
                    first_announced_at=v["first_announced_at"],
                    first_announced_precision=v["first_announced_precision"],
                    announcement_title=v["announcement_title"],
                    announcement_url=v["announcement_url"],
                    categories=by_version.get(v["id"], []),
                )
            )
    items = [
        ModelFamily(
            slug=f["slug"],
            family_name=f["family_name"],
            company=CompanyRef(slug=f["company_slug"], name=f["company_name"]),
            versions=versions.get(f["id"], []),
        )
        for f in families
    ]
    return Page[ModelFamily](
        items=items, total=total, page=page, page_size=page_size, pages=page_count(total, page_size)
    )


def _public_error(message: str | None) -> str | None:
    """Last error text safe to show publicly (no internal exception details)."""
    if not message:
        return None
    if message.startswith(("processing failed", "invalid relevance rules", "fetch failed")):
        return "Internal processing error."
    return message[:200]


@router.get("/sources", response_model=list[Source])
async def list_sources(
    conn: Annotated[AsyncConnection, Depends(get_connection)],
    company: Slug | None = None,
) -> list[Source]:
    """Configured official sources with their real synchronisation state."""
    rows = (
        (
            await conn.execute(
                text(
                    """
SELECT s.id, s.name, s.kind, s.url, s.hosting, s.hosting_notes, s.content_scope,
  s.verification_level, s.verified_at, s.verification_notes, s.poll_interval_minutes,
  s.status, s.consecutive_failures, s.last_synced_at, s.last_error,
  c.slug AS company_slug, c.name AS company_name,
  (SELECT count(*) FROM announcements a WHERE a.source_id = s.id) AS announcement_count,
  r.status AS run_status, r.started_at AS run_started_at, r.finished_at AS run_finished_at,
  r.http_status AS run_http_status, r.items_found, r.items_new, r.items_filtered
FROM sources s JOIN companies c ON c.id = s.company_id
LEFT JOIN LATERAL (
  SELECT * FROM sync_runs x WHERE x.source_id = s.id ORDER BY x.started_at DESC, x.id DESC LIMIT 1
) r ON true
WHERE (CAST(:company AS text) IS NULL OR c.slug = :company)
ORDER BY lower(c.name), lower(s.name), s.id
"""
                ),
                {"company": company},
            )
        )
        .mappings()
        .all()
    )
    return [
        Source(
            id=r["id"],
            name=r["name"],
            company=CompanyRef(slug=r["company_slug"], name=r["company_name"]),
            kind=r["kind"],
            url=r["url"],
            hosting=r["hosting"],
            hosting_notes=r["hosting_notes"],
            content_scope=r["content_scope"],
            verification_level=r["verification_level"],
            verified_at=r["verified_at"],
            verification_notes=r["verification_notes"],
            poll_interval_minutes=r["poll_interval_minutes"],
            enabled=r["status"] != "disabled",
            status=r["status"],
            consecutive_failures=r["consecutive_failures"],
            last_synced_at=r["last_synced_at"],
            last_error=_public_error(r["last_error"]),
            announcement_count=r["announcement_count"],
            last_run=(
                SourceRun(
                    status=r["run_status"],
                    started_at=r["run_started_at"],
                    finished_at=r["run_finished_at"],
                    http_status=r["run_http_status"],
                    items_found=r["items_found"],
                    items_new=r["items_new"],
                    items_filtered=r["items_filtered"],
                )
                if r["run_status"] is not None
                else None
            ),
        )
        for r in rows
    ]


@router.get("/meta", response_model=Meta)
async def get_meta(conn: Annotated[AsyncConnection, Depends(get_connection)]) -> Meta:
    """Real totals for the interface (no estimates)."""
    row = (
        (
            await conn.execute(
                text(
                    "SELECT (SELECT count(*) FROM announcements) AS announcements, "
                    "(SELECT count(*) FROM companies) AS companies, "
                    "(SELECT count(*) FROM sources) AS sources, "
                    "(SELECT count(*) FROM sources WHERE status IS DISTINCT FROM 'disabled') AS enabled, "
                    "(SELECT max(last_synced_at) FROM sources) AS last_synced_at"
                )
            )
        )
        .mappings()
        .one()
    )
    return Meta(
        announcement_count=row["announcements"],
        company_count=row["companies"],
        source_count=row["sources"],
        enabled_source_count=row["enabled"],
        last_synced_at=row["last_synced_at"],
    )
