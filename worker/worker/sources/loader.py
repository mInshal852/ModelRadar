"""Load and cross-validate the YAML configuration in config/."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import yaml
from pydantic import BaseModel, ValidationError

from worker.sources.schema import CategoriesFile, CategoryNode, CompanyConfig

EXPECTED_TOP_LEVEL_CATEGORIES = 17


@dataclass(frozen=True)
class LoadedConfig:
    categories: list[CategoryNode]
    companies: list[CompanyConfig]

    def category_slugs(self) -> set[str]:
        slugs = {c.slug for c in self.categories}
        slugs |= {child.slug for c in self.categories for child in c.children}
        return slugs


def normalize_url(url: str) -> str:
    """Normalise a URL for duplicate detection (case of scheme/host, fragment, trailing slash)."""
    p = urlparse(url.strip())
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), (p.hostname or "").lower(), path, "", p.query, ""))


def _read_yaml(path: Path, errors: list[str]) -> Any | None:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
        errors.append(f"{path.name}: cannot read YAML: {exc}")
        return None


def _validate_model[T: BaseModel](
    model: type[T], data: Any, path: Path, errors: list[str]
) -> T | None:
    if not isinstance(data, dict):
        errors.append(f"{path.name}: top level must be a mapping")
        return None
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors():
            where = ".".join(str(part) for part in err["loc"]) or "(root)"
            errors.append(f"{path.name}: {where}: {err['msg']}")
        return None


def _load_categories(
    config_dir: Path, errors: list[str], expected_top_level: int | None
) -> list[CategoryNode]:
    path = config_dir / "categories.yaml"
    if not path.exists():
        errors.append("categories.yaml: file not found")
        return []
    parsed = _validate_model(CategoriesFile, _read_yaml(path, errors), path, errors)
    if parsed is None:
        return []
    if expected_top_level is not None and len(parsed.categories) != expected_top_level:
        errors.append(
            f"categories.yaml: expected {expected_top_level} top-level categories, "
            f"got {len(parsed.categories)}"
        )
    seen: set[str] = set()
    for node in parsed.categories:
        for slug in [node.slug, *(child.slug for child in node.children)]:
            if slug in seen:
                errors.append(f"categories.yaml: duplicate category slug '{slug}'")
            seen.add(slug)
    return parsed.categories


def _load_companies(config_dir: Path, errors: list[str]) -> list[CompanyConfig]:
    companies: list[CompanyConfig] = []
    for path in sorted((config_dir / "companies").glob("*.y*ml")):
        if path.suffix != ".yaml":
            errors.append(f"{path.name}: use the .yaml extension")
            continue
        company = _validate_model(CompanyConfig, _read_yaml(path, errors), path, errors)
        if company is None:
            continue
        if path.stem != company.slug:
            errors.append(f"{path.name}: file name must match the company slug '{company.slug}'")
        companies.append(company)
    return companies


def _check_cross_references(
    categories: list[CategoryNode], companies: list[CompanyConfig], errors: list[str]
) -> None:
    known = {c.slug for c in categories} | {ch.slug for c in categories for ch in c.children}
    company_slugs: set[str] = set()
    source_slugs: dict[str, str] = {}
    source_urls: dict[str, str] = {}

    for company in companies:
        if company.slug in company_slugs:
            errors.append(f"duplicate company slug '{company.slug}'")
        company_slugs.add(company.slug)

        for category in company.categories:
            if category not in known:
                errors.append(f"{company.slug}: unknown category '{category}'")

        for source in company.sources:
            if source.slug in source_slugs:
                errors.append(
                    f"duplicate source slug '{source.slug}' "
                    f"(also in '{source_slugs[source.slug]}')"
                )
            source_slugs[source.slug] = company.slug

            url_key = normalize_url(source.url)
            if url_key in source_urls:
                errors.append(
                    f"duplicate source URL {source.url} ('{source.slug}' and "
                    f"'{source_urls[url_key]}')"
                )
            source_urls[url_key] = source.slug


def validate_config_dir(
    config_dir: Path, expected_top_level: int | None = EXPECTED_TOP_LEVEL_CATEGORIES
) -> tuple[LoadedConfig | None, list[str]]:
    """Return (config, errors). `config` is None when any error was found.

    `expected_top_level` is the approved number of top-level categories (17); tests with small
    synthetic configs pass None to skip that check.
    """
    errors: list[str] = []
    categories = _load_categories(config_dir, errors, expected_top_level)
    companies = _load_companies(config_dir, errors)
    _check_cross_references(categories, companies, errors)
    if errors:
        return None, errors
    return LoadedConfig(categories=categories, companies=companies), []


class ConfigError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def load_config(config_dir: Path) -> LoadedConfig:
    config, errors = validate_config_dir(config_dir)
    if config is None:
        raise ConfigError(errors)
    return config
