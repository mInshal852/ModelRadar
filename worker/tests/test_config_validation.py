import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from worker.sources.loader import ConfigError, load_config, normalize_url, validate_config_dir
from worker.sources.schema import INGESTIBLE_KINDS

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"

BASE_SOURCE: dict[str, Any] = {
    "slug": "acme-blog",
    "name": "Acme blog",
    "kind": "rss",
    "url": "https://acme.test/feed.xml",
    "hosting": "first_party",
    "content_scope": "dedicated_ai",
    "verification_level": "content_sampled",
    "verified_at": "2026-01-01",
    "verification_notes": "Test fixture source.",
    "poll_interval_minutes": 60,
}
BASE_COMPANY: dict[str, Any] = {
    "slug": "acme",
    "name": "Acme AI",
    "website_url": "https://acme.test",
    "categories": ["cat-one"],
    "sources": [BASE_SOURCE],
}

Builder = Callable[..., Path]


def company(**overrides: Any) -> dict[str, Any]:
    data = copy.deepcopy(BASE_COMPANY)
    data.update(overrides)
    return data


def source(**overrides: Any) -> dict[str, Any]:
    data = copy.deepcopy(BASE_SOURCE)
    data.update(overrides)
    return data


def errors_for(make_config: Builder, **companies: dict[str, Any]) -> list[str]:
    files = {f"{name}.yaml": yaml.safe_dump(data) for name, data in companies.items()}
    config, errors = validate_config_dir(make_config(companies=files), expected_top_level=None)
    assert (config is None) == bool(errors)
    return errors


def assert_error(errors: list[str], fragment: str) -> None:
    assert any(fragment in e for e in errors), f"{fragment!r} not in {errors}"


# --- the real repository configuration --------------------------------------------------


def test_repository_config_is_valid() -> None:
    config, errors = validate_config_dir(REPO_CONFIG)
    assert errors == []
    assert config is not None
    assert len(config.categories) == 17


def test_repository_config_matches_the_approved_first_batch() -> None:
    config = load_config(REPO_CONFIG)
    enabled = {s.slug for c in config.companies for s in c.sources if s.enabled}
    assert enabled == {
        "google-deepmind-blog",
        "google-ai-blog",
        "mistral-news",
        "allen-ai-news",
        "stability-ai-news",
        "midjourney-updates",
        "pika-blog",
        "voyage-ai-blog",
        "anthropic-api-release-notes",
        "openai-news",
    }


def test_repository_sources_are_official_and_honestly_recorded() -> None:
    config = load_config(REPO_CONFIG)
    for c in config.companies:
        for s in c.sources:
            assert s.kind in INGESTIBLE_KINDS or not s.enabled
            assert s.verification_notes.strip()
            if s.enabled:
                assert s.verification_level != "http_only"
                assert s.verified_at is not None
            else:
                assert s.disabled_reason


# --- valid configuration ----------------------------------------------------------------


def test_valid_config_loads(make_config: Builder) -> None:
    assert errors_for(make_config, acme=company()) == []


def test_load_config_raises_with_all_errors(make_config: Builder) -> None:
    root = make_config(companies={"acme.yaml": yaml.safe_dump(company(categories=["nope"]))})
    with pytest.raises(ConfigError) as info:
        load_config(root)  # default requires 17 categories as well
    assert len(info.value.errors) >= 2


# --- structure and required fields ------------------------------------------------------


def test_invalid_yaml_is_reported(make_config: Builder) -> None:
    root = make_config(companies={"acme.yaml": "slug: [unclosed"})
    _, errors = validate_config_dir(root, expected_top_level=None)
    assert_error(errors, "cannot read YAML")


def test_top_level_must_be_mapping(make_config: Builder) -> None:
    root = make_config(companies={"acme.yaml": "- just\n- a list\n"})
    _, errors = validate_config_dir(root, expected_top_level=None)
    assert_error(errors, "top level must be a mapping")


@pytest.mark.parametrize("field", ["slug", "name", "website_url", "categories", "sources"])
def test_company_required_fields(make_config: Builder, field: str) -> None:
    data = company()
    del data[field]
    assert_error(errors_for(make_config, acme=data), field)


@pytest.mark.parametrize(
    "field",
    [
        "slug",
        "name",
        "kind",
        "url",
        "hosting",
        "content_scope",
        "verification_notes",
        "poll_interval_minutes",
    ],
)
def test_source_required_fields(make_config: Builder, field: str) -> None:
    src = source()
    del src[field]
    assert_error(errors_for(make_config, acme=company(sources=[src])), field)


def test_unknown_fields_are_rejected(make_config: Builder) -> None:
    errors = errors_for(make_config, acme=company(surprise="x"))
    assert_error(errors, "surprise")


# --- value validation -------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides,fragment",
    [
        ({"kind": "carrier_pigeon"}, "kind"),
        ({"hosting": "self_hosted"}, "hosting"),
        ({"content_scope": "everything"}, "content_scope"),
        ({"verification_level": "trust_me"}, "verification_level"),
        ({"poll_interval_minutes": 5}, "poll_interval_minutes"),
        ({"poll_interval_minutes": 100000}, "poll_interval_minutes"),
        ({"poll_interval_minutes": "often"}, "poll_interval_minutes"),
        ({"url": "ftp://acme.test/feed"}, "http"),
        ({"url": "not a url"}, "http"),
        ({"url": "https://user:pw@acme.test/feed"}, "credentials"),
        ({"slug": "Not A Slug"}, "slug"),
    ],
)
def test_invalid_source_values(
    make_config: Builder, overrides: dict[str, Any], fragment: str
) -> None:
    errors = errors_for(make_config, acme=company(sources=[source(**overrides)]))
    assert_error(errors, fragment)


def test_invalid_company_values(make_config: Builder) -> None:
    assert_error(errors_for(make_config, acme=company(country="usa")), "country")
    assert_error(errors_for(make_config, acme=company(website_url="acme.test")), "http")
    assert_error(errors_for(make_config, acme=company(official_domains=["HTTP://x"])), "domain")


def test_verification_requires_a_date(make_config: Builder) -> None:
    src = source()
    del src["verified_at"]
    assert_error(errors_for(make_config, acme=company(sources=[src])), "verified_at")


def test_third_party_hosting_needs_notes(make_config: Builder) -> None:
    src = source(hosting="official_third_party")
    assert_error(errors_for(make_config, acme=company(sources=[src])), "hosting_notes")


def test_disabled_sources_need_a_reason_and_enabled_must_not_have_one(
    make_config: Builder,
) -> None:
    assert_error(
        errors_for(make_config, acme=company(sources=[source(enabled=False)])), "disabled_reason"
    )
    assert_error(
        errors_for(make_config, acme=company(sources=[source(disabled_reason="because")])),
        "disabled_reason",
    )
    assert (
        errors_for(
            make_config, acme=company(sources=[source(enabled=False, disabled_reason="blocked")])
        )
        == []
    )


def test_non_feed_kinds_must_stay_disabled(make_config: Builder) -> None:
    html = source(kind="html", extractor_config={"item": "article"})
    assert_error(errors_for(make_config, acme=company(sources=[html])), "cannot be enabled yet")
    html["enabled"] = False
    html["disabled_reason"] = "HTML extraction is not implemented yet"
    assert errors_for(make_config, acme=company(sources=[html])) == []


def test_feed_sources_reject_extractor_config(make_config: Builder) -> None:
    errors = errors_for(make_config, acme=company(sources=[source(extractor_config={"a": 1})]))
    assert_error(errors, "extractor_config")


def test_invalid_relevance_regex(make_config: Builder) -> None:
    rules = {"include_title_patterns": ["(unclosed"]}
    errors = errors_for(make_config, acme=company(sources=[source(relevance_rules=rules)]))
    assert_error(errors, "invalid regular expression")


# --- references and official domains ----------------------------------------------------


def test_unknown_category_reference(make_config: Builder) -> None:
    assert_error(errors_for(make_config, acme=company(categories=["ghost"])), "unknown category")


def test_child_categories_are_valid_references(make_config: Builder) -> None:
    assert errors_for(make_config, acme=company(categories=["cat-one-a", "cat-two"])) == []


def test_duplicate_company_categories(make_config: Builder) -> None:
    assert_error(
        errors_for(make_config, acme=company(categories=["cat-one", "cat-one"])), "duplicate"
    )


def test_source_must_be_on_an_official_domain(make_config: Builder) -> None:
    src = source(url="https://evil.example/feed.xml")
    assert_error(errors_for(make_config, acme=company(sources=[src])), "not an official domain")


def test_lookalike_domain_is_not_official(make_config: Builder) -> None:
    src = source(url="https://notacme.test/feed.xml")
    assert_error(errors_for(make_config, acme=company(sources=[src])), "not an official domain")


def test_subdomains_and_declared_domains_are_official(make_config: Builder) -> None:
    sub = source(url="https://blog.acme.test/feed.xml")
    assert errors_for(make_config, acme=company(sources=[sub])) == []
    extra = source(url="https://acme-cdn.test/feed.xml")
    assert (
        errors_for(make_config, acme=company(official_domains=["acme-cdn.test"], sources=[extra]))
        == []
    )


# --- duplicates -------------------------------------------------------------------------


def test_duplicate_company_slugs_across_files(make_config: Builder) -> None:
    other = company(
        sources=[source(slug="other", url="https://acme.test/other.xml")],
    )
    errors = errors_for(make_config, acme=company(), beta=other)
    assert_error(errors, "duplicate company slug 'acme'")
    assert_error(errors, "file name must match")


def test_duplicate_source_slugs_in_one_company(make_config: Builder) -> None:
    a = source()
    b = source(url="https://acme.test/other.xml")
    assert_error(errors_for(make_config, acme=company(sources=[a, b])), "duplicate source slug")


def test_duplicate_source_slugs_across_companies(make_config: Builder) -> None:
    beta = {
        **company(slug="beta", website_url="https://beta.test"),
        "sources": [source(url="https://beta.test/feed.xml")],  # same slug 'acme-blog'
    }
    assert_error(errors_for(make_config, acme=company(), beta=beta), "duplicate source slug")


def test_duplicate_source_urls_even_when_formatted_differently(make_config: Builder) -> None:
    a = source(slug="one", url="https://acme.test/feed.xml")
    b = source(slug="two", url="HTTPS://ACME.test/feed.xml/#top")
    assert_error(errors_for(make_config, acme=company(sources=[a, b])), "duplicate source URL")


def test_normalize_url() -> None:
    assert normalize_url("HTTPS://Example.COM/a/b/#x") == normalize_url("https://example.com/a/b")
    assert normalize_url("https://e.com/a?x=1") != normalize_url("https://e.com/a?x=2")


def test_duplicate_category_slugs(make_config: Builder) -> None:
    cats = """
    categories:
      - slug: dup
        name: One
      - slug: dup
        name: Two
    """
    root = make_config(categories=cats)
    _, errors = validate_config_dir(root, expected_top_level=None)
    assert_error(errors, "duplicate category slug")


def test_category_count_is_enforced_by_default(make_config: Builder) -> None:
    _, errors = validate_config_dir(make_config())
    assert_error(errors, "expected 17 top-level categories")
