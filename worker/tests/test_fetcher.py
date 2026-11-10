import httpx
import pytest

from tests.feeds import ScriptedServer, ok, rss, rss_item
from worker.ingest.fetcher import DomainLimiter
from worker.sources.verify import USER_AGENT

URL = "https://acme.test/feed.xml"
FEED = rss(rss_item())


async def test_successful_fetch_sends_identifying_user_agent() -> None:
    server = ScriptedServer(
        ok(FEED, etag='"v1"', **{"last-modified": "Mon, 02 Nov 2026 10:00:00 GMT"})
    )
    outcome = await server.fetcher().fetch(URL)
    assert outcome.kind == "ok" and outcome.status == 200 and outcome.content == FEED
    assert (outcome.etag, outcome.last_modified) == ('"v1"', "Mon, 02 Nov 2026 10:00:00 GMT")
    assert all(r.headers["user-agent"] == USER_AGENT for r in server.requests)
    assert "ModelRadar" in USER_AGENT and "github.com" in USER_AGENT


async def test_conditional_headers_are_sent_when_validators_exist() -> None:
    server = ScriptedServer(httpx.Response(304))
    outcome = await server.fetcher().fetch(URL, '"v1"', "Mon, 02 Nov 2026 10:00:00 GMT")
    request = server.feed_requests()[0]
    assert request.headers["if-none-match"] == '"v1"'
    assert request.headers["if-modified-since"] == "Mon, 02 Nov 2026 10:00:00 GMT"
    assert outcome.kind == "not_modified" and outcome.status == 304
    assert outcome.etag == '"v1"'  # validators are kept on 304


async def test_no_conditional_headers_without_validators() -> None:
    server = ScriptedServer(ok(FEED))
    await server.fetcher().fetch(URL)
    headers = server.feed_requests()[0].headers
    assert "if-none-match" not in headers and "if-modified-since" not in headers


async def test_permanent_errors_are_not_retried() -> None:
    for status in (401, 403, 404, 410):
        server = ScriptedServer(httpx.Response(status))
        outcome = await server.fetcher().fetch(URL)
        assert outcome.kind == "error" and outcome.status == status
        assert len(server.feed_requests()) == 1, status  # no retries, no workarounds
        assert server.sleeps == []


async def test_server_errors_are_retried_with_exponential_backoff_then_succeed() -> None:
    server = ScriptedServer(httpx.Response(503), httpx.Response(502), ok(FEED))
    outcome = await server.fetcher(max_attempts=3, backoff_base_seconds=1.0).fetch(URL)
    assert outcome.kind == "ok" and outcome.attempts == 3
    assert server.sleeps == [1.0, 2.0]


async def test_retries_are_bounded() -> None:
    server = ScriptedServer(httpx.Response(500))
    outcome = await server.fetcher(max_attempts=3).fetch(URL)
    assert outcome.kind == "error" and outcome.status == 500 and outcome.attempts == 3
    assert len(server.feed_requests()) == 3


async def test_rate_limit_429_honours_short_retry_after() -> None:
    server = ScriptedServer(httpx.Response(429, headers={"retry-after": "7"}), ok(FEED))
    outcome = await server.fetcher(backoff_base_seconds=1.0).fetch(URL)
    assert outcome.kind == "ok"
    assert server.sleeps == [7.0]  # waits at least as long as the server asked


async def test_rate_limit_with_very_long_retry_after_gives_up() -> None:
    server = ScriptedServer(httpx.Response(429, headers={"retry-after": "86400"}))
    outcome = await server.fetcher(max_retry_after_seconds=60.0).fetch(URL)
    assert outcome.kind == "error" and outcome.status == 429
    assert len(server.feed_requests()) == 1
    assert "Retry-After" in (outcome.error or "")


async def test_network_errors_and_timeouts_are_transient() -> None:
    request = httpx.Request("GET", URL)
    server = ScriptedServer(httpx.ConnectTimeout("slow", request=request), ok(FEED))
    outcome = await server.fetcher().fetch(URL)
    assert outcome.kind == "ok" and outcome.attempts == 2

    failing = ScriptedServer(httpx.ReadTimeout("slow", request=request))
    outcome = await failing.fetcher(max_attempts=2).fetch(URL)
    assert outcome.kind == "error" and outcome.status is None
    assert "ReadTimeout" in (outcome.error or "")


async def test_robots_txt_disallow_is_respected() -> None:
    server = ScriptedServer(ok(FEED), robots="User-agent: *\nDisallow: /feed.xml\n")
    outcome = await server.fetcher().fetch(URL)
    assert outcome.kind == "error" and "robots.txt" in (outcome.error or "")
    assert server.feed_requests() == []  # the feed itself was never requested


async def test_robots_txt_allowing_rules_are_followed() -> None:
    server = ScriptedServer(ok(FEED), robots="User-agent: *\nDisallow: /private/\n")
    assert (await server.fetcher().fetch(URL)).kind == "ok"


async def test_robots_txt_server_error_means_do_not_fetch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(503)
            if request.url.path == "/robots.txt"
            else httpx.Response(200, content=FEED)
        )

    server = ScriptedServer()
    server.handler = handler  # type: ignore[method-assign]
    outcome = await server.fetcher(max_attempts=2).fetch(URL)
    assert outcome.kind == "error" and "robots.txt unavailable" in (outcome.error or "")


async def test_robots_txt_is_fetched_once_per_origin() -> None:
    server = ScriptedServer(ok(FEED))
    fetcher = server.fetcher()
    await fetcher.fetch(URL)
    await fetcher.fetch("https://acme.test/other.xml")
    robots_requests = [r for r in server.requests if r.url.path == "/robots.txt"]
    assert len(robots_requests) == 1


async def test_domain_limiter_spaces_requests_to_the_same_host() -> None:
    now = [0.0]
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    limiter = DomainLimiter(2.0, sleep=fake_sleep, clock=lambda: now[0])
    await limiter.wait("a.test")  # first request: no wait
    await limiter.wait("a.test")  # must wait the full interval
    await limiter.wait("b.test")  # different host: no wait
    now[0] += 5.0
    await limiter.wait("a.test")  # enough time has passed
    assert waits == [2.0]


async def test_oversized_responses_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("worker.ingest.fetcher.MAX_BODY_BYTES", 10)
    outcome = await ScriptedServer(ok(FEED)).fetcher().fetch(URL)
    assert outcome.kind == "error" and "too large" in (outcome.error or "")
