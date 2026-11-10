"""Pydantic schema for config/categories.yaml and config/companies/*.yaml."""

import re
from datetime import date
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN, max_length=80)]

SourceKind = Literal["rss", "atom", "github", "api", "sitemap", "html", "manual"]
Hosting = Literal["first_party", "official_third_party"]
ContentScope = Literal["dedicated_ai", "mixed"]
VerificationLevel = Literal["http_only", "content_sampled", "content_verified"]

# Only feed sources can be enabled in this phase; other kinds are configurable but must stay
# disabled until their ingestion exists.
INGESTIBLE_KINDS = frozenset({"rss", "atom"})

DOMAIN_PATTERN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def validate_http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must start with http:// or https://")
    if not parsed.hostname:
        raise ValueError("URL has no host")
    if parsed.username or parsed.password:
        raise ValueError("URL must not contain credentials")
    if re.search(r"\s", value):
        raise ValueError("URL must not contain whitespace")
    return value


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


class RelevanceRules(StrictModel):
    """Filter for mixed-content sources.

    - Exclusions always win.
    - If any include_* list is non-empty, an item must match at least one include rule.
    - `*_categories` match the feed's own category/tag terms (case-insensitive, exact).
    - `*_patterns` are case-insensitive regular expressions searched in the title / URL.
    """

    include_categories: list[str] = Field(default_factory=list)
    exclude_categories: list[str] = Field(default_factory=list)
    include_title_patterns: list[str] = Field(default_factory=list)
    exclude_title_patterns: list[str] = Field(default_factory=list)
    include_url_patterns: list[str] = Field(default_factory=list)
    exclude_url_patterns: list[str] = Field(default_factory=list)

    @field_validator(
        "include_title_patterns",
        "exclude_title_patterns",
        "include_url_patterns",
        "exclude_url_patterns",
    )
    @classmethod
    def _patterns_compile(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                raise ValueError(f"invalid regular expression {pattern!r}: {exc}") from exc
        return patterns

    @field_validator("include_categories", "exclude_categories")
    @classmethod
    def _no_blank_terms(cls, terms: list[str]) -> list[str]:
        if any(not t.strip() for t in terms):
            raise ValueError("category terms must not be blank")
        return terms

    def is_empty(self) -> bool:
        return not any(self.model_dump().values())


class SourceConfig(StrictModel):
    slug: Slug
    name: str = Field(min_length=1)
    kind: SourceKind
    url: str
    hosting: Hosting
    hosting_notes: str | None = None
    content_scope: ContentScope
    verification_level: VerificationLevel = "http_only"
    verified_at: date | None = None
    verification_notes: str = Field(min_length=1)
    poll_interval_minutes: int = Field(ge=15, le=10080)
    enabled: bool = True
    disabled_reason: str | None = None
    relevance_rules: RelevanceRules | None = None
    extractor_config: dict[str, Any] | None = None

    @field_validator("url")
    @classmethod
    def _valid_url(cls, value: str) -> str:
        return validate_http_url(value)

    @model_validator(mode="after")
    def _consistency(self) -> "SourceConfig":
        if self.enabled and self.disabled_reason:
            raise ValueError("disabled_reason must be empty for an enabled source")
        if not self.enabled and not self.disabled_reason:
            raise ValueError("a disabled source needs a disabled_reason")
        if self.enabled and self.kind not in INGESTIBLE_KINDS:
            raise ValueError(
                f"kind '{self.kind}' cannot be enabled yet (ingestion is not implemented); "
                "set enabled: false"
            )
        if self.verification_level != "http_only" and self.verified_at is None:
            raise ValueError("verified_at is required when verification_level is above http_only")
        if self.hosting == "official_third_party" and not self.hosting_notes:
            raise ValueError("hosting_notes must explain third-party hosting")
        if self.kind in INGESTIBLE_KINDS and self.extractor_config is not None:
            raise ValueError("extractor_config does not apply to RSS/Atom sources")
        return self


class CompanyConfig(StrictModel):
    slug: Slug
    name: str = Field(min_length=1)
    website_url: str
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    description: str | None = None
    # Extra domains (besides website_url's) that this company officially owns or publishes on.
    official_domains: list[str] = Field(default_factory=list)
    categories: list[Slug] = Field(min_length=1)
    sources: list[SourceConfig] = Field(min_length=1)

    @field_validator("website_url")
    @classmethod
    def _valid_website(cls, value: str) -> str:
        return validate_http_url(value)

    @field_validator("official_domains")
    @classmethod
    def _valid_domains(cls, domains: list[str]) -> list[str]:
        for domain in domains:
            if not DOMAIN_PATTERN.match(domain):
                raise ValueError(f"invalid domain {domain!r} (lowercase hostname, no scheme)")
        return domains

    @field_validator("categories")
    @classmethod
    def _unique_categories(cls, slugs: list[str]) -> list[str]:
        if len(set(slugs)) != len(slugs):
            raise ValueError("duplicate category in company categories")
        return slugs

    def domains(self) -> set[str]:
        site = host_of(self.website_url).removeprefix("www.")
        return {site, *self.official_domains}

    @model_validator(mode="after")
    def _sources_on_official_domains(self) -> "CompanyConfig":
        domains = self.domains()
        for source in self.sources:
            host = host_of(source.url)
            if not any(host_matches(host, d) for d in domains):
                raise ValueError(
                    f"source '{source.slug}' host '{host}' is not an official domain of "
                    f"'{self.slug}' ({', '.join(sorted(domains))}); add it to official_domains "
                    "only if the company officially owns it"
                )
        return self


class CategoryChild(StrictModel):
    slug: Slug
    name: str = Field(min_length=1)


class CategoryNode(StrictModel):
    slug: Slug
    name: str = Field(min_length=1)
    children: list[CategoryChild] = Field(default_factory=list)

    @field_validator("children", mode="before")
    @classmethod
    def _none_is_empty(cls, value: object) -> object:
        return [] if value is None else value


class CategoriesFile(StrictModel):
    categories: list[CategoryNode]
