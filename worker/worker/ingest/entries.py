"""Turn feed bytes into validated, filtered entries ready to store.

Nothing is invented: titles and URLs are kept as published, missing descriptions and dates
stay None, and no model names or categories are derived.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse, urlunparse

import feedparser

from worker.ingest.dates import Precision, parse_entry_date
from worker.sources.relevance import is_relevant
from worker.sources.schema import RelevanceRules

MAX_ENTRIES = 5000
MAX_DESCRIPTION_CHARS = 10000


@dataclass
class ParsedEntry:
    title: str
    url: str
    description: str | None
    published_at: Any  # datetime | None
    published_precision: Precision | None
    content_hash: str
    metadata: dict[str, Any] | None


@dataclass
class ParseResult:
    recognised: bool = False
    found: int = 0
    invalid: int = 0
    filtered: int = 0
    duplicates_in_feed: int = 0
    entries: list[ParsedEntry] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


class _TextExtractor(HTMLParser):
    _BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "pre"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip += 1
        elif tag in self._BLOCK:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(value: str) -> str:
    """Plain text of a feed description: tags removed, entities decoded, whitespace collapsed."""
    extractor = _TextExtractor()
    extractor.feed(value)
    extractor.close()
    return re.sub(r"\s+", " ", unescape("".join(extractor.parts))).strip()


def announcement_url_key(url: str) -> str:
    """Key for recognising the same URL written slightly differently.

    Lowercases scheme and host and drops a trailing slash. The query and the fragment are
    kept: some feeds (for example release notes) distinguish entries only by fragment.
    The stored original URL is never changed.
    """
    p = urlparse(url.strip())
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), (p.hostname or "").lower(), path, "", p.query, p.fragment))


def compute_content_hash(title: str, url: str, description: str | None) -> str:
    payload = json.dumps([title, url, description], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _valid_url(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in {"http", "https"} and bool(p.hostname) and not re.search(r"\s", url)


def parse_feed(content: bytes, rules: RelevanceRules | None) -> ParseResult:
    result = ParseResult()
    parsed = feedparser.parse(content)
    if not parsed.get("version") and not parsed.entries:
        result.problems.append("not a recognisable RSS/Atom feed")
        return result
    result.recognised = True
    if parsed.bozo:
        result.problems.append("feed parsed with errors (malformed XML or encoding)")

    seen: set[str] = set()
    for entry in parsed.entries[:MAX_ENTRIES]:
        result.found += 1
        title = (entry.get("title") or "").strip()
        url = (entry.get("link") or "").strip()
        if not title or not _valid_url(url):
            result.invalid += 1
            continue

        terms = [t.get("term", "").strip() for t in entry.get("tags", []) if t.get("term")]
        if not is_relevant(rules, title=title, url=url, categories=terms):
            result.filtered += 1
            continue

        key = announcement_url_key(url)
        if key in seen:
            result.duplicates_in_feed += 1
            continue
        seen.add(key)

        raw_summary = (entry.get("summary") or "").strip()
        description: str | None = html_to_text(raw_summary) or None
        metadata: dict[str, Any] = {}
        if description and len(description) > MAX_DESCRIPTION_CHARS:
            description = description[:MAX_DESCRIPTION_CHARS]
            metadata["description_truncated"] = True
        if terms:
            metadata["feed_categories"] = terms

        raw_date = entry.get("published") or entry.get("updated")
        struct = entry.get("published_parsed")  # feedparser falls back to the updated date
        published_at, precision = parse_entry_date(raw_date, struct)

        result.entries.append(
            ParsedEntry(
                title=title,
                url=url,
                description=description,
                published_at=published_at,
                published_precision=precision,
                content_hash=compute_content_hash(title, url, description),
                metadata=metadata or None,
            )
        )
    return result
