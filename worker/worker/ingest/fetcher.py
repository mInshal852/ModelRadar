"""Polite, conditional HTTP fetching of feeds.

- Identifies itself with a clear User-Agent; respects robots.txt (RFC 9309 semantics).
- Per-domain minimum interval between requests.
- Conditional requests (If-None-Match / If-Modified-Since).
- Exponential backoff with jitter for transient errors (network, 429, 5xx), honouring a
  short Retry-After. Permanent errors (401/403/404/410, other 4xx) are not retried.
- Never bypasses blocks, CAPTCHAs or access restrictions: a refusal is reported as-is.
"""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Literal
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from worker.sources.verify import USER_AGENT

MAX_BODY_BYTES = 15 * 1024 * 1024
TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


@dataclass
class FetchSettings:
    timeout_seconds: float = 20.0
    max_attempts: int = 3
    backoff_base_seconds: float = 2.0
    max_retry_after_seconds: float = 60.0
    domain_min_interval_seconds: float = 2.0


@dataclass
class FetchOutcome:
    kind: Literal["ok", "not_modified", "error"]
    status: int | None = None
    content: bytes = b""
    etag: str | None = None
    last_modified: str | None = None
    error: str | None = None
    attempts: int = 1


Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


class DomainLimiter:
    """Ensures a minimum delay between requests to the same host."""

    def __init__(
        self, min_interval: float, sleep: Sleep = asyncio.sleep, clock: Clock = time.monotonic
    ) -> None:
        self._min = min_interval
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            last = self._last.get(host)
            if last is not None:
                delay = self._min - (self._clock() - last)
                if delay > 0:
                    await self._sleep(delay)
            self._last[host] = self._clock()


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
        return float(max(0.0, when.timestamp() - time.time()))
    except (TypeError, ValueError):
        return None


class _RobotsUnavailable(Exception):
    pass


class FeedFetcher:
    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: FetchSettings | None = None,
        sleep: Sleep = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._client = client
        self.settings = settings or FetchSettings()
        self._sleep = sleep
        self._jitter = jitter
        self._limiter = DomainLimiter(self.settings.domain_min_interval_seconds, sleep)
        self._robots: dict[str, RobotFileParser | None] = {}

    # --- robots.txt ----------------------------------------------------------------------

    async def _robots_allows(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            self._robots[origin] = await self._load_robots(origin)
        parser = self._robots[origin]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    async def _load_robots(self, origin: str) -> RobotFileParser | None:
        """None means 'no robots.txt rules' (all allowed). Raises if it cannot be determined."""
        outcome = await self._request(f"{origin}/robots.txt", {}, check_robots=False)
        if outcome.kind == "error":
            if outcome.status is not None and 400 <= outcome.status < 500:
                return None  # RFC 9309: unavailable (4xx) means no restrictions
            raise _RobotsUnavailable(outcome.error or "robots.txt unavailable")
        if outcome.kind == "not_modified":
            return None
        parser = RobotFileParser()
        parser.parse(outcome.content.decode("utf-8", errors="replace").splitlines())
        return parser

    # --- requests ------------------------------------------------------------------------

    async def fetch(
        self, url: str, etag: str | None = None, last_modified: str | None = None
    ) -> FetchOutcome:
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        return await self._request(url, headers, check_robots=True)

    async def _request(
        self, url: str, headers: dict[str, str], *, check_robots: bool
    ) -> FetchOutcome:
        if check_robots:
            try:
                if not await self._robots_allows(url):
                    return FetchOutcome("error", error="disallowed by robots.txt")
            except _RobotsUnavailable as exc:
                return FetchOutcome("error", error=f"robots.txt unavailable: {exc}")

        host = urlparse(url).netloc
        last = FetchOutcome("error", error="no request attempted")
        for attempt in range(1, self.settings.max_attempts + 1):
            await self._limiter.wait(host)
            retry_after: float | None = None
            try:
                response = await self._client.get(
                    url,
                    headers={"User-Agent": USER_AGENT, **headers},
                    timeout=self.settings.timeout_seconds,
                )
            except httpx.HTTPError as exc:
                last = FetchOutcome(
                    "error", error=f"request failed ({type(exc).__name__})", attempts=attempt
                )
            else:
                if response.status_code == 304:
                    return FetchOutcome(
                        "not_modified",
                        status=304,
                        etag=response.headers.get("etag") or headers.get("If-None-Match"),
                        last_modified=response.headers.get("last-modified")
                        or headers.get("If-Modified-Since"),
                        attempts=attempt,
                    )
                if response.status_code == 200:
                    if len(response.content) > MAX_BODY_BYTES:
                        return FetchOutcome(
                            "error", status=200, error="response too large", attempts=attempt
                        )
                    return FetchOutcome(
                        "ok",
                        status=200,
                        content=response.content,
                        etag=response.headers.get("etag"),
                        last_modified=response.headers.get("last-modified"),
                        attempts=attempt,
                    )
                last = FetchOutcome(
                    "error",
                    status=response.status_code,
                    error=f"HTTP {response.status_code}",
                    attempts=attempt,
                )
                if response.status_code not in TRANSIENT_STATUSES:
                    return last  # permanent (401/403/404/410/...): do not retry or work around
                retry_after = _retry_after_seconds(response)
                if retry_after is not None and retry_after > self.settings.max_retry_after_seconds:
                    last.error = (
                        f"HTTP {response.status_code} (Retry-After {int(retry_after)}s too long)"
                    )
                    return last

            if attempt < self.settings.max_attempts:
                delay = self.settings.backoff_base_seconds * (2 ** (attempt - 1))
                delay += delay * 0.25 * self._jitter()
                if retry_after is not None:
                    delay = max(delay, retry_after)
                await self._sleep(delay)
        return last
