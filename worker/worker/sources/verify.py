"""Feed verification: fetch a feed and inspect its real content.

An HTTP 200 is NOT treated as proof that a source is suitable. A report records what the
feed actually contains (titles, links, dates, categories, hosts, freshness), notes missing
or inconsistent fields honestly, and never invents values. Nothing here stores announcements.
"""

import calendar
import datetime as dt
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import httpx

from worker.sources.relevance import is_relevant
from worker.sources.schema import SourceConfig, host_matches

USER_AGENT = (
    "ModelRadar/0.1 (+https://github.com/mInshal852/ModelRadar; read-only source verification)"
)
STALE_WARN_DAYS = 180
STALE_FAIL_DAYS = 365
MIN_USABLE_RATIO = 0.9

Verdict = Literal["pass", "pass_with_warnings", "fail"]


@dataclass
class FeedStats:
    entries: int = 0
    with_title: int = 0
    with_link: int = 0
    with_date: int = 0
    with_summary: int = 0
    duplicate_links: int = 0
    off_domain_links: int = 0
    newest: dt.datetime | None = None
    oldest: dt.datetime | None = None
    newest_age_days: int | None = None
    link_hosts: dict[str, int] = field(default_factory=dict)
    categories: dict[str, int] = field(default_factory=dict)
    kept_by_rules: int = 0
    filtered_by_rules: int = 0
    feed_version: str = ""


@dataclass
class VerificationReport:
    source_slug: str
    url: str
    http_status: int | None = None
    content_type: str | None = None
    verdict: Verdict = "fail"
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: FeedStats | None = None


@dataclass
class FetchResult:
    status: int | None
    content_type: str | None
    content: bytes
    error: str | None = None


def _robots_allows(client: httpx.Client, url: str) -> tuple[bool, str | None]:
    """RFC 9309 behaviour: 4xx robots.txt means allowed; 5xx/unreachable means do not fetch."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = client.get(robots_url)
    except httpx.HTTPError as exc:
        return False, f"robots.txt unreachable ({type(exc).__name__})"
    if 400 <= response.status_code < 500:
        return True, None
    if response.status_code != 200:
        return False, f"robots.txt returned HTTP {response.status_code}"
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    if parser.can_fetch(USER_AGENT, url):
        return True, None
    return False, "disallowed by robots.txt"


def fetch_feed(client: httpx.Client, url: str) -> FetchResult:
    """Fetch a feed politely. Never bypasses blocks: a refusal is reported as-is."""
    allowed, reason = _robots_allows(client, url)
    if not allowed:
        return FetchResult(None, None, b"", error=reason)
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        return FetchResult(None, None, b"", error=f"request failed ({type(exc).__name__})")
    return FetchResult(response.status_code, response.headers.get("content-type"), response.content)


def _entry_datetime(entry: feedparser.FeedParserDict) -> dt.datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return dt.datetime.fromtimestamp(calendar.timegm(parsed), dt.UTC)


def inspect_feed(
    content: bytes,
    source: SourceConfig,
    company_domains: set[str],
    now: dt.datetime,
) -> VerificationReport:
    """Inspect feed bytes (no network). Used by `verify_source` and directly by tests."""
    report = VerificationReport(source_slug=source.slug, url=source.url)
    parsed = feedparser.parse(content)
    entries = parsed.entries
    stats = FeedStats(entries=len(entries), feed_version=parsed.get("version", "") or "")
    report.stats = stats

    if not entries:
        reason = (
            "not a recognisable RSS/Atom feed"
            if parsed.bozo or not parsed.get("version")
            else "feed has no entries"
        )
        report.problems.append(reason)
        return report
    if parsed.bozo:
        report.warnings.append("feed parsed with errors (malformed XML or encoding)")

    dates: list[dt.datetime] = []
    links: list[str] = []
    hosts: Counter[str] = Counter()
    categories: Counter[str] = Counter()

    for entry in entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        terms = [t.get("term", "") for t in entry.get("tags", []) if t.get("term")]
        stats.with_title += bool(title)
        stats.with_link += bool(link)
        stats.with_summary += bool((entry.get("summary") or "").strip())
        when = _entry_datetime(entry)
        if when:
            stats.with_date += 1
            dates.append(when)
        if link:
            links.append(link)
            host = (urlparse(link).hostname or "").lower()
            hosts[host] += 1
            if not any(host_matches(host, d) for d in company_domains):
                stats.off_domain_links += 1
        categories.update(terms)
        if is_relevant(source.relevance_rules, title=title, url=link, categories=terms):
            stats.kept_by_rules += 1
        else:
            stats.filtered_by_rules += 1

    stats.duplicate_links = len(links) - len(set(links))
    stats.link_hosts = dict(hosts)
    stats.categories = dict(categories.most_common(15))
    if dates:
        stats.newest, stats.oldest = max(dates), min(dates)
        stats.newest_age_days = (now - stats.newest).days

    _judge(report, stats, source)
    return report


def _judge(report: VerificationReport, stats: FeedStats, source: SourceConfig) -> None:
    n = stats.entries
    if stats.with_title / n < MIN_USABLE_RATIO:
        report.problems.append(f"only {stats.with_title}/{n} entries have a title")
    elif stats.with_title < n:
        report.warnings.append(f"{n - stats.with_title}/{n} entries have no title")
    if stats.with_link / n < MIN_USABLE_RATIO:
        report.problems.append(f"only {stats.with_link}/{n} entries have a link")
    elif stats.with_link < n:
        report.warnings.append(f"{n - stats.with_link}/{n} entries have no link")

    if stats.with_date == 0:
        report.warnings.append("no entry has a publication date (published_at would be NULL)")
    elif stats.with_date < n:
        report.warnings.append(
            f"{n - stats.with_date}/{n} entries have no publication date (kept as NULL)"
        )

    if stats.with_summary < n:
        report.warnings.append(
            f"{n - stats.with_summary}/{n} entries have no description (kept as NULL)"
        )
    if stats.duplicate_links:
        report.warnings.append(f"{stats.duplicate_links} duplicate link(s) in the feed")
    if stats.off_domain_links:
        share = stats.off_domain_links / n
        message = f"{stats.off_domain_links}/{n} links point outside the company's official domains"
        (report.problems if share > 0.5 else report.warnings).append(message)

    if stats.newest_age_days is not None:
        if stats.newest_age_days > STALE_FAIL_DAYS:
            report.problems.append(f"stale: newest entry is {stats.newest_age_days} days old")
        elif stats.newest_age_days > STALE_WARN_DAYS:
            report.warnings.append(f"newest entry is {stats.newest_age_days} days old")

    if stats.kept_by_rules == 0:
        report.problems.append("relevance rules filter out every entry")

    version = stats.feed_version
    if source.kind == "atom" and not version.startswith("atom"):
        report.warnings.append(f"configured as atom but feed reports '{version}'")
    if source.kind == "rss" and not version.startswith(("rss", "rdf")):
        report.warnings.append(f"configured as rss but feed reports '{version}'")

    if report.problems:
        report.verdict = "fail"
    elif report.warnings:
        report.verdict = "pass_with_warnings"
    else:
        report.verdict = "pass"


def verify_source(
    client: httpx.Client,
    source: SourceConfig,
    company_domains: set[str],
    now: dt.datetime | None = None,
) -> VerificationReport:
    """Fetch and inspect one feed source."""
    now = now or dt.datetime.now(dt.UTC)
    fetched = fetch_feed(client, source.url)
    report = VerificationReport(
        source_slug=source.slug,
        url=source.url,
        http_status=fetched.status,
        content_type=fetched.content_type,
    )
    if fetched.error:
        report.problems.append(fetched.error)
        return report
    if fetched.status != 200:
        report.problems.append(f"HTTP {fetched.status}")
        return report
    inspected = inspect_feed(fetched.content, source, company_domains, now)
    inspected.http_status = fetched.status
    inspected.content_type = fetched.content_type
    return inspected


def make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    )
