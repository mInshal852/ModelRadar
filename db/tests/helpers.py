"""Small SQL helpers for tests. These insert only synthetic rows inside rolled-back
transactions of disposable test databases; no data ever reaches the development database."""

from sqlalchemy import Connection, text


def insert_company(conn: Connection, slug: str = "acme") -> int:
    return int(
        conn.execute(
            text(
                "INSERT INTO companies (slug, name, website_url) "
                "VALUES (:slug, 'Test Co', 'https://example.test') RETURNING id"
            ),
            {"slug": slug},
        ).scalar_one()
    )


def insert_source(conn: Connection, company_id: int, url: str = "https://example.test/feed") -> int:
    return int(
        conn.execute(
            text(
                "INSERT INTO sources (company_id, name, kind, url, hosting, content_scope, "
                "poll_interval_minutes) VALUES (:c, 'Test feed', 'rss', :url, 'first_party', "
                "'mixed', 30) RETURNING id"
            ),
            {"c": company_id, "url": url},
        ).scalar_one()
    )


def insert_announcement(
    conn: Connection,
    company_id: int,
    source_id: int,
    original_url: str = "https://example.test/post-1",
    published_at: str | None = None,
    precision: str | None = None,
) -> int:
    return int(
        conn.execute(
            text(
                "INSERT INTO announcements (company_id, source_id, title, original_url, "
                "content_hash, published_at, published_precision) "
                "VALUES (:c, :s, 'Title', :u, 'hash', :p, :prec) RETURNING id"
            ),
            {
                "c": company_id,
                "s": source_id,
                "u": original_url,
                "p": published_at,
                "prec": precision,
            },
        ).scalar_one()
    )


def seed_announcement(conn: Connection) -> tuple[int, int, int]:
    company = insert_company(conn)
    source = insert_source(conn, company)
    announcement = insert_announcement(conn, company, source)
    return company, source, announcement
