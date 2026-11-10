"""Relevance filtering for mixed-content sources (no classification, only keep/drop)."""

import re
from collections.abc import Iterable

from worker.sources.schema import RelevanceRules


def _any_match(patterns: Iterable[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def is_relevant(
    rules: RelevanceRules | None,
    *,
    title: str,
    url: str,
    categories: Iterable[str] = (),
) -> bool:
    """Decide whether a feed item should be kept.

    Exclusions always win. If any include rule exists, the item must satisfy at least one.
    With no rules, every item is kept.
    """
    if rules is None or rules.is_empty():
        return True

    terms = {c.strip().casefold() for c in categories}
    exclude_cats = {c.casefold() for c in rules.exclude_categories}
    if terms & exclude_cats:
        return False
    if _any_match(rules.exclude_title_patterns, title):
        return False
    if _any_match(rules.exclude_url_patterns, url):
        return False

    include_cats = {c.casefold() for c in rules.include_categories}
    has_includes = bool(include_cats or rules.include_title_patterns or rules.include_url_patterns)
    if not has_includes:
        return True
    return bool(
        terms & include_cats
        or _any_match(rules.include_title_patterns, title)
        or _any_match(rules.include_url_patterns, url)
    )
