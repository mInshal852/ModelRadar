import datetime as dt
from typing import Any

import httpx
import pytest
from fastapi.routing import APIRoute
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import app

TOTAL = 6 + 25  # synthetic announcements in the seed


async def get(client: httpx.AsyncClient, path: str, **params: Any) -> httpx.Response:
    return await client.get(path, params={k: v for k, v in params.items() if v is not None})


async def titles(client: httpx.AsyncClient, **params: Any) -> list[str]:
    response = await get(client, "/v1/announcements", page_size=100, **params)
    assert response.status_code == 200, response.text
    return [i["title"] for i in response.json()["items"]]


# --- announcements: shape, sorting, dates ----------------------------------------------------


async def test_announcement_shape(client: httpx.AsyncClient) -> None:
    body = (await get(client, "/v1/announcements", q="Alpha")).json()
    item = body["items"][0]
    assert item["title"] == "Alpha model released"  # exactly as stored
    assert item["description"] == "Alpha is a new model."
    assert item["kind"] == "model_release"
    assert item["original_url"] == "https://acme.test/alpha"
    assert item["source_domain"] == "acme.test"
    assert item["source_name"] == "Acme feed"
    assert item["company"] == {"slug": "acme", "name": "Acme Labs"}
    assert item["published_at"].startswith("2026-11-05T10:30:00")
    assert item["published_precision"] == "datetime"
    assert item["models"] == ["Alpha 1"]
    assert "first_seen_at" not in item  # discovery time is not part of the public record
    assert set(item) == {
        "id", "title", "description", "kind", "published_at", "published_precision",
        "original_url", "source_domain", "source_name", "company", "categories", "models",
    }  # fmt: skip


async def test_sorted_by_publication_date_with_undated_last(client: httpx.AsyncClient) -> None:
    items = (await get(client, "/v1/announcements", page_size=100)).json()["items"]
    dated = [i["published_at"] for i in items if i["published_at"]]
    assert dated == sorted(dated, reverse=True)
    assert items[-1]["title"] == "Undated post" and items[-1]["published_at"] is None
    assert all(i["published_at"] for i in items[:-1])


async def test_missing_description_and_date_are_null_not_invented(
    client: httpx.AsyncClient,
) -> None:
    items = {
        i["title"]: i
        for i in (await get(client, "/v1/announcements", page_size=100)).json()["items"]
    }
    assert items["Epsilon launch"]["description"] is None
    undated = items["Undated post"]
    assert (undated["published_at"], undated["published_precision"]) == (None, None)


async def test_day_precision_is_reported(client: httpx.AsyncClient) -> None:
    items = {
        i["title"]: i
        for i in (await get(client, "/v1/announcements", page_size=100)).json()["items"]
    }
    assert items["Notes without a time"]["published_precision"] == "day"


# --- pagination ------------------------------------------------------------------------------


async def test_pagination_is_server_side(client: httpx.AsyncClient) -> None:
    first = (await get(client, "/v1/announcements", page=1, page_size=10)).json()
    second = (await get(client, "/v1/announcements", page=2, page_size=10)).json()
    assert (first["total"], first["page"], first["page_size"], first["pages"]) == (TOTAL, 1, 10, 4)
    assert len(first["items"]) == 10 and len(second["items"]) == 10
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}
    last = (await get(client, "/v1/announcements", page=4, page_size=10)).json()
    assert len(last["items"]) == TOTAL - 30


async def test_page_beyond_the_end_is_empty(client: httpx.AsyncClient) -> None:
    body = (await get(client, "/v1/announcements", page=99, page_size=10)).json()
    assert body["items"] == [] and body["total"] == TOTAL


async def test_default_page_size_and_limits(client: httpx.AsyncClient) -> None:
    assert len((await get(client, "/v1/announcements")).json()["items"]) == 20
    assert (await get(client, "/v1/announcements", page_size=101)).status_code == 422
    assert (await get(client, "/v1/announcements", page_size=0)).status_code == 422
    assert (await get(client, "/v1/announcements", page=0)).status_code == 422


# --- filters and search ----------------------------------------------------------------------


async def test_company_filter(client: httpx.AsyncClient) -> None:
    assert len(await titles(client, company="acme")) == 4
    assert await titles(client, company="gamma") == []


async def test_kind_filter(client: httpx.AsyncClient) -> None:
    assert sorted(await titles(client, kind="model_release")) == [
        "Alpha model released",
        "Epsilon launch",
    ]
    assert await titles(client, kind="deprecation") == []


async def test_category_filter_includes_children_and_inherited_categories(
    client: httpx.AsyncClient,
) -> None:
    # acme inherits cat-a1 (child of cat-a); the research post has its OWN category cat-b.
    in_a = await titles(client, category="cat-a")
    assert sorted(in_a) == ["Alpha model released", "Notes without a time", "Undated post"]
    assert sorted(await titles(client, category="cat-a1")) == sorted(in_a)
    in_b = await titles(client, category="cat-b")
    assert "Delta research paper" in in_b and "Epsilon launch" in in_b
    assert "Alpha model released" not in in_b


async def test_announcement_categories_prefer_own_over_company(client: httpx.AsyncClient) -> None:
    items = {
        i["title"]: i
        for i in (await get(client, "/v1/announcements", page_size=100)).json()["items"]
    }
    assert [c["slug"] for c in items["Alpha model released"]["categories"]] == ["cat-a1"]
    assert [c["slug"] for c in items["Delta research paper"]["categories"]] == ["cat-b"]


async def test_date_range_filter_excludes_undated(client: httpx.AsyncClient) -> None:
    got = await titles(client, published_from="2026-11-05", published_to="2026-11-05")
    assert sorted(got) == ["Alpha model released", "Notes without a time"]
    assert "Undated post" not in await titles(client, published_from="2000-01-01")
    assert await titles(client, published_to="2000-01-01") == []


async def test_date_range_validation(client: httpx.AsyncClient) -> None:
    response = await get(
        client, "/v1/announcements", published_from="2026-11-06", published_to="2026-11-01"
    )
    assert response.status_code == 422
    assert (await get(client, "/v1/announcements", published_from="not-a-date")).status_code == 422


async def test_search_matches_title_words_and_prefixes(client: httpx.AsyncClient) -> None:
    assert await titles(client, q="alpha") == ["Alpha model released"]
    assert await titles(client, q="Alph") == ["Alpha model released"]  # partial title match
    assert await titles(client, q="new model") == ["Alpha model released"]  # description words


async def test_search_with_no_match(client: httpx.AsyncClient) -> None:
    body = (await get(client, "/v1/announcements", q="zzzzzz")).json()
    assert body["items"] == [] and body["total"] == 0 and body["pages"] == 0


async def test_search_treats_wildcards_literally(client: httpx.AsyncClient) -> None:
    assert await titles(client, q="100%") == ["Discount 100% off_now"]
    assert await titles(client, q="off_now") == ["Discount 100% off_now"]
    assert await titles(client, q="%") == ["Discount 100% off_now"]


async def test_search_is_safe_against_sql_and_odd_input(client: httpx.AsyncClient) -> None:
    for q in ["'; DROP TABLE announcements; --", '"unbalanced', "a & | ! ( )", "\\"]:
        response = await get(client, "/v1/announcements", q=q)
        assert response.status_code == 200, q
    assert (await get(client, "/v1/announcements")).json()["total"] == TOTAL
    assert (await get(client, "/v1/announcements", q="x" * 101)).status_code == 422


async def test_filters_combine(client: httpx.AsyncClient) -> None:
    assert await titles(client, company="acme", kind="model_release", q="alpha") == [
        "Alpha model released"
    ]
    assert await titles(client, company="beta", kind="research") == []


async def test_invalid_filter_values_are_rejected(client: httpx.AsyncClient) -> None:
    assert (await get(client, "/v1/announcements", kind="press")).status_code == 422
    assert (await get(client, "/v1/announcements", company="Not A Slug!")).status_code == 422


# --- categories, companies, models, sources, meta ----------------------------------------------


async def test_categories_tree_with_real_counts(client: httpx.AsyncClient) -> None:
    tree = (await client.get("/v1/categories")).json()
    assert [c["slug"] for c in tree] == ["cat-a", "cat-b"]
    cat_a, cat_b = tree
    assert [c["slug"] for c in cat_a["children"]] == ["cat-a1"]
    assert (
        cat_a["announcement_count"] == 3
    )  # three acme posts inherit it; the research post is cat-b
    assert cat_a["children"][0]["announcement_count"] == 3
    assert cat_b["announcement_count"] == 28  # beta's 27 + the research post with its own category
    assert cat_a["company_count"] == 1 and cat_b["company_count"] == 1
    assert cat_a["description"] is None


async def test_companies(client: httpx.AsyncClient) -> None:
    body = (await client.get("/v1/companies")).json()
    assert [c["slug"] for c in body["items"]] == ["acme", "beta", "gamma"]
    acme, beta, gamma = body["items"]
    assert (acme["country"], acme["description"]) == ("US", "Test company.")
    assert (beta["country"], beta["description"]) == (None, None)
    assert acme["announcement_count"] == 4 and gamma["announcement_count"] == 0
    assert gamma["latest_published_at"] is None and gamma["categories"] == []
    assert [c["slug"] for c in acme["categories"]] == ["cat-a1"]
    assert acme["source_count"] == 2 and beta["source_count"] == 3


async def test_company_filters_and_detail(client: httpx.AsyncClient) -> None:
    assert [
        c["slug"] for c in (await get(client, "/v1/companies", category="cat-a")).json()["items"]
    ] == ["acme"]
    assert [c["slug"] for c in (await get(client, "/v1/companies", q="works")).json()["items"]] == [
        "beta"
    ]
    assert (await client.get("/v1/companies/acme")).json()["name"] == "Acme Labs"
    missing = await client.get("/v1/companies/nope")
    assert missing.status_code == 404
    assert missing.json() == {"error": {"code": "not_found", "message": "Resource not found."}}


async def test_models(client: httpx.AsyncClient) -> None:
    body = (await client.get("/v1/models")).json()
    assert body["total"] == 1
    family = body["items"][0]
    assert (family["family_name"], family["company"]["slug"]) == ("Alpha", "acme")
    version = family["versions"][0]
    assert version["display_name"] == "Alpha 1"
    assert version["announcement_url"] == "https://acme.test/alpha"
    assert version["first_announced_precision"] == "datetime"
    assert [c["slug"] for c in version["categories"]] == ["cat-a1"]
    assert (await get(client, "/v1/models", company="beta")).json()["items"] == []
    assert (await get(client, "/v1/models", q="alpha 1")).json()["total"] == 1


async def test_sources(client: httpx.AsyncClient) -> None:
    sources = {s["name"]: s for s in (await client.get("/v1/sources")).json()}
    assert len(sources) == 5
    ok = sources["Acme feed"]
    assert (ok["status"], ok["enabled"], ok["announcement_count"]) == ("ok", True, 4)
    assert ok["last_synced_at"].startswith("2026-11-08T09:00")
    assert ok["last_run"]["items_found"] == 7 and ok["last_run"]["status"] == "success"
    failing = sources["Beta feed"]
    assert (failing["status"], failing["last_error"], failing["last_synced_at"]) == (
        "failing",
        "HTTP 403",
        None,
    )
    assert failing["last_run"]["http_status"] == 403
    assert sources["Beta old feed"]["enabled"] is False
    never = sources["Acme never synced"]
    assert (never["status"], never["last_synced_at"], never["last_run"]) == (None, None, None)


async def test_sources_do_not_expose_internal_details(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/sources")
    for source in response.json():
        assert not {"etag", "last_modified", "extractor_config", "relevance_rules"} & set(source)
    assert "secret" not in response.text  # etag value, exception text
    broken = {s["name"]: s for s in response.json()}["Beta broken"]
    assert broken["last_error"] == "Internal processing error."


async def test_sources_company_filter(client: httpx.AsyncClient) -> None:
    got = (await get(client, "/v1/sources", company="acme")).json()
    assert {s["company"]["slug"] for s in got} == {"acme"}


async def test_meta_counts_are_real(client: httpx.AsyncClient) -> None:
    meta = (await client.get("/v1/meta")).json()
    assert meta["announcement_count"] == TOTAL
    assert (meta["company_count"], meta["source_count"], meta["enabled_source_count"]) == (3, 5, 4)
    assert meta["last_synced_at"].startswith("2026-11-08T09:00")


# --- errors -------------------------------------------------------------------------------------


async def test_validation_errors_have_a_consistent_shape(client: httpx.AsyncClient) -> None:
    response = await get(client, "/v1/announcements", page_size=500)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["field"] == "page_size"


async def test_unknown_route_uses_the_error_format(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/nothing-here")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_unexpected_errors_do_not_leak_details(client: httpx.AsyncClient) -> None:
    from app.db import get_connection

    async def broken() -> Any:
        raise RuntimeError("password=hunter2 host=internal-db")
        yield  # pragma: no cover

    previous = app.dependency_overrides[get_connection]
    app.dependency_overrides[get_connection] = broken
    try:
        response = await client.get("/v1/announcements")
    finally:
        app.dependency_overrides[get_connection] = previous
    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "The service could not complete the request.",
        }
    }
    assert "hunter2" not in response.text


# --- read-only behaviour -------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
@pytest.mark.parametrize(
    "path", ["/v1/announcements", "/v1/categories", "/v1/companies", "/v1/sources"]
)
async def test_write_methods_are_not_allowed(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path, json={})
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_every_route_is_get_only() -> None:
    for route in app.routes:
        if isinstance(route, APIRoute):
            assert route.methods <= {"GET", "HEAD", "OPTIONS"}, route.path


async def test_api_database_session_cannot_write(api_engine: AsyncEngine) -> None:
    """Even with a bug in a query, the API's database session could not modify data."""
    for sql in (
        "DELETE FROM announcements",
        "UPDATE announcements SET title = 'x'",
        "INSERT INTO companies (slug, name, website_url) VALUES ('x', 'x', 'https://x.test')",
        "DROP TABLE announcements",
    ):
        with pytest.raises(DBAPIError):
            async with api_engine.begin() as conn:
                await conn.execute(text(sql))
    async with api_engine.connect() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM announcements"))).scalar_one()
    assert count == TOTAL


async def test_dates_are_utc(client: httpx.AsyncClient) -> None:
    item = (await get(client, "/v1/announcements", q="Alpha")).json()["items"][0]
    parsed = dt.datetime.fromisoformat(item["published_at"])
    assert parsed.utcoffset() == dt.timedelta(0)
