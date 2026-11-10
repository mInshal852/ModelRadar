"""Controlled feed fixtures and a scripted HTTP server for tests.

All XML here is synthetic test input for the parser and ingestion code. It is never loaded
into the development database and never used outside tests.
"""

from collections.abc import Callable

import httpx

from worker.ingest.fetcher import FeedFetcher, FetchSettings


def rss_item(
    title: str | None = "Hello world",
    link: str | None = "https://acme.test/posts/1",
    date: str | None = "Mon, 02 Nov 2026 10:00:00 GMT",
    desc: str | None = "A short description.",
    cats: tuple[str, ...] = (),
) -> str:
    parts: list[str] = []
    if title is not None:
        parts.append(f"<title>{title}</title>")
    if link is not None:
        parts.append(f"<link>{link}</link>")
    if date is not None:
        parts.append(f"<pubDate>{date}</pubDate>")
    if desc is not None:
        parts.append(f"<description>{desc}</description>")
    parts += [f"<category>{c}</category>" for c in cats]
    return f"<item>{''.join(parts)}</item>"


def rss(*items: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>t</title>'
        f"<link>https://acme.test</link><description>d</description>{''.join(items)}"
        "</channel></rss>"
    ).encode()


def atom_entry(
    title: str | None = "Atom post",
    link: str | None = "https://acme.test/atom/1",
    updated: str | None = "2026-11-01T12:00:00Z",
    published: str | None = None,
    summary: str | None = "Atom summary",
) -> str:
    parts = ["<id>urn:x</id>"]
    if title is not None:
        parts.append(f"<title>{title}</title>")
    if link is not None:
        parts.append(f'<link href="{link}"/>')
    if updated is not None:
        parts.append(f"<updated>{updated}</updated>")
    if published is not None:
        parts.append(f"<published>{published}</published>")
    if summary is not None:
        parts.append(f"<summary>{summary}</summary>")
    return f"<entry>{''.join(parts)}</entry>"


def atom(*entries: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom">'
        f"<title>t</title><id>urn:feed</id><updated>2026-11-01T00:00:00Z</updated>"
        f"{''.join(entries)}</feed>"
    ).encode()


class ScriptedServer:
    """Mock web server. `feed_responses` are returned in order (the last one repeats)."""

    def __init__(
        self, *feed_responses: httpx.Response | Exception, robots: str | None = None
    ) -> None:
        self.feed_responses = list(feed_responses)
        self.robots = robots
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []

    def feed_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path != "/robots.txt"]

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/robots.txt":
            if self.robots is None:
                return httpx.Response(404)
            return httpx.Response(200, text=self.robots)
        index = min(len(self.feed_requests()) - 1, len(self.feed_responses) - 1)
        item = self.feed_responses[index]
        if isinstance(item, Exception):
            raise item
        return item

    def fetcher(self, **settings: float) -> FeedFetcher:
        defaults: dict[str, float] = {
            "domain_min_interval_seconds": 0.0,
            "backoff_base_seconds": 1.0,
        }
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
        return FeedFetcher(
            client,
            FetchSettings(**{**defaults, **settings}),  # type: ignore[arg-type]
            sleep=self.sleep,
            jitter=lambda: 0.0,
        )


def ok(content: bytes, **headers: str) -> httpx.Response:
    return httpx.Response(200, content=content, headers=headers)


FetcherFactory = Callable[..., FeedFetcher]
