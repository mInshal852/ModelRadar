"""Feed parsing / content verification tests.

The XML below is synthetic test input for the parser. It is never loaded into any database.
"""

import datetime as dt
from collections.abc import Callable

import httpx

from worker.sources.schema import RelevanceRules, SourceConfig
from worker.sources.verify import USER_AGENT, inspect_feed, verify_source

NOW = dt.datetime(2026, 11, 10, tzinfo=dt.UTC)
DOMAINS = {"acme.test"}


def make_source(**overrides: object) -> SourceConfig:
    data: dict[str, object] = {
        "slug": "acme-blog",
        "name": "Acme blog",
        "kind": "rss",
        "url": "https://acme.test/feed.xml",
        "hosting": "first_party",
        "content_scope": "dedicated_ai",
        "verification_notes": "test",
        "poll_interval_minutes": 60,
    }
    data.update(overrides)
    return SourceConfig.model_validate(data)


def rss(*items: str) -> bytes:
    body = "".join(items)
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
        f"<link>https://acme.test</link><description>d</description>{body}</channel></rss>"
    ).encode()


def item(
    title: str | None = "Hello",
    link: str | None = "https://acme.test/a",
    date: str | None = "Mon, 02 Nov 2026 10:00:00 GMT",
    desc: str | None = "Body",
    cats: tuple[str, ...] = (),
) -> str:
    parts = []
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


ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>t</title><id>x</id>
<updated>2026-11-01T00:00:00Z</updated>
<entry><title>An Atom post</title><id>1</id>
<link href="https://acme.test/atom-1"/><updated>2026-11-01T00:00:00Z</updated>
<summary>Atom summary</summary></entry></feed>"""


# --- parsing and content inspection ------------------------------------------------------


def test_good_rss_feed_passes() -> None:
    report = inspect_feed(
        rss(item(), item(link="https://acme.test/b")), make_source(), DOMAINS, NOW
    )
    assert report.verdict == "pass"
    assert report.stats is not None
    assert (report.stats.entries, report.stats.with_date, report.stats.with_summary) == (2, 2, 2)


def test_atom_feed_is_parsed() -> None:
    source = make_source(kind="atom")
    report = inspect_feed(ATOM, source, DOMAINS, NOW)
    assert report.verdict == "pass"
    assert report.stats is not None
    assert report.stats.feed_version.startswith("atom")
    assert report.stats.link_hosts == {"acme.test": 1}


def test_missing_dates_and_descriptions_are_reported_not_invented() -> None:
    xml = rss(item(date=None, desc=None), item(link="https://acme.test/b"))
    report = inspect_feed(xml, make_source(), DOMAINS, NOW)
    assert report.verdict == "pass_with_warnings"
    assert report.stats is not None
    assert (report.stats.with_date, report.stats.with_summary) == (1, 1)
    assert any("no publication date" in w for w in report.warnings)
    assert any("no description" in w for w in report.warnings)


def test_feed_where_no_entry_has_a_date_still_reports_honestly() -> None:
    report = inspect_feed(rss(item(date=None)), make_source(), DOMAINS, NOW)
    assert report.stats is not None
    assert report.stats.newest is None and report.stats.oldest is None
    assert any("published_at would be NULL" in w for w in report.warnings)


def test_entries_without_titles_or_links_fail() -> None:
    xml = rss(item(title=None), item(title=None, link="https://acme.test/b"))
    assert inspect_feed(xml, make_source(), DOMAINS, NOW).verdict == "fail"
    xml = rss(item(link=None), item(link=None))
    assert inspect_feed(xml, make_source(), DOMAINS, NOW).verdict == "fail"


def test_empty_feed_fails() -> None:
    report = inspect_feed(rss(), make_source(), DOMAINS, NOW)
    assert report.verdict == "fail"
    assert "no entries" in report.problems[0]


def test_html_instead_of_a_feed_fails() -> None:
    html = b"<html><body><h1>Blog</h1><p>Not a feed</p></body></html>"
    report = inspect_feed(html, make_source(), DOMAINS, NOW)
    assert report.verdict == "fail"
    assert "not a recognisable" in report.problems[0]


def test_garbage_bytes_fail() -> None:
    assert inspect_feed(b"\x00\x01\x02 not xml", make_source(), DOMAINS, NOW).verdict == "fail"


def test_stale_feeds_warn_then_fail() -> None:
    ancient = "Sun, 01 Jun 2025 00:00:00 GMT"  # ~527 days before NOW
    report = inspect_feed(rss(item(date=ancient)), make_source(), DOMAINS, NOW)
    assert report.verdict == "fail" and "stale" in report.problems[0]
    recent = "Thu, 01 Oct 2026 00:00:00 GMT"
    assert inspect_feed(rss(item(date=recent)), make_source(), DOMAINS, NOW).verdict == "pass"
    older = "Fri, 01 May 2026 00:00:00 GMT"  # ~193 days
    report = inspect_feed(rss(item(date=older)), make_source(), DOMAINS, NOW)
    assert report.verdict == "pass_with_warnings"
    assert any("days old" in w for w in report.warnings)


def test_off_domain_links_are_flagged() -> None:
    mixed = rss(item(), item(link="https://elsewhere.test/x"), item(link="https://acme.test/c"))
    report = inspect_feed(mixed, make_source(), DOMAINS, NOW)
    assert report.verdict == "pass_with_warnings"
    mostly_off = rss(item(link="https://x.test/1"), item(link="https://y.test/2"))
    assert inspect_feed(mostly_off, make_source(), DOMAINS, NOW).verdict == "fail"


def test_duplicate_links_are_flagged() -> None:
    report = inspect_feed(rss(item(), item()), make_source(), DOMAINS, NOW)
    assert report.stats is not None and report.stats.duplicate_links == 1
    assert report.verdict == "pass_with_warnings"


# --- relevance filtering inside verification ---------------------------------------------


def test_relevance_rules_are_applied_to_feed_categories() -> None:
    xml = rss(
        item(link="https://acme.test/1", cats=("Product",)),
        item(link="https://acme.test/2", cats=("Story",)),
        item(link="https://acme.test/3"),
    )
    rules = RelevanceRules(include_categories=["Product"])
    report = inspect_feed(xml, make_source(relevance_rules=rules), DOMAINS, NOW)
    assert report.stats is not None
    assert (report.stats.kept_by_rules, report.stats.filtered_by_rules) == (1, 2)
    assert report.stats.categories == {"Product": 1, "Story": 1}


def test_rules_that_remove_everything_fail() -> None:
    rules = RelevanceRules(include_categories=["Nothing"])
    report = inspect_feed(rss(item()), make_source(relevance_rules=rules), DOMAINS, NOW)
    assert report.verdict == "fail"
    assert "filter out every entry" in report.problems[0]


# --- network behaviour (mock transport; no real requests) ---------------------------------


def client_for(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})


def serve(feed: bytes, robots: str | None = None) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404 if robots is None else 200, text=robots or "")
        return httpx.Response(200, content=feed, headers={"content-type": "application/xml"})

    return handler


def test_verify_source_success_and_identifies_itself() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        return serve(rss(item()))(request)

    report = verify_source(client_for(handler), make_source(), DOMAINS, NOW)
    assert report.verdict == "pass" and report.http_status == 200
    assert all(ua == USER_AGENT for ua in seen)


def test_http_error_status_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(404, text="nope")

    report = verify_source(client_for(handler), make_source(), DOMAINS, NOW)
    assert report.verdict == "fail" and report.problems == ["HTTP 404"]


def test_blocked_access_is_reported_not_bypassed() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(403, text="forbidden")

    report = verify_source(client_for(handler), make_source(), DOMAINS, NOW)
    assert report.verdict == "fail" and report.problems == ["HTTP 403"]
    assert requests.count("/feed.xml") == 1  # no retries, no alternate tricks


def test_unreachable_source_fails_cleanly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    report = verify_source(client_for(handler), make_source(), DOMAINS, NOW)
    assert report.verdict == "fail"
    assert report.http_status is None
    assert "unreachable" in report.problems[0] or "failed" in report.problems[0]


def test_robots_txt_disallow_is_respected() -> None:
    client = client_for(serve(rss(item()), robots="User-agent: *\nDisallow: /feed.xml\n"))
    report = verify_source(client, make_source(), DOMAINS, NOW)
    assert report.verdict == "fail" and "robots.txt" in report.problems[0]


def test_robots_server_error_means_do_not_fetch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    report = verify_source(client_for(handler), make_source(), DOMAINS, NOW)
    assert report.verdict == "fail" and "robots.txt" in report.problems[0]


def test_html_page_served_with_200_is_not_accepted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text="<html><body>Hi</body></html>")

    report = verify_source(client_for(handler), make_source(), DOMAINS, NOW)
    assert report.http_status == 200
    assert report.verdict == "fail"  # HTTP 200 alone is not proof of a usable feed
