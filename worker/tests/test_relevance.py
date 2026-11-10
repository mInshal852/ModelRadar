from worker.sources.relevance import is_relevant
from worker.sources.schema import RelevanceRules


def rules(**kwargs: list[str]) -> RelevanceRules:
    return RelevanceRules(**kwargs)


def test_no_rules_keeps_everything() -> None:
    assert is_relevant(None, title="Anything", url="https://x.test/a")
    assert is_relevant(rules(), title="Anything", url="https://x.test/a")


def test_include_categories_requires_a_match_case_insensitively() -> None:
    r = rules(include_categories=["Product", "Safety & Alignment"])
    assert is_relevant(r, title="t", url="u", categories=["product"])
    assert is_relevant(r, title="t", url="u", categories=["Other", "SAFETY & ALIGNMENT"])
    assert not is_relevant(r, title="t", url="u", categories=["Company"])


def test_untagged_items_are_dropped_when_includes_exist() -> None:
    r = rules(include_categories=["Product"])
    assert not is_relevant(r, title="Customer story", url="u", categories=[])


def test_exclusions_win_over_inclusions() -> None:
    r = rules(include_categories=["Product"], exclude_categories=["Story"])
    assert not is_relevant(r, title="t", url="u", categories=["Product", "Story"])


def test_exclude_only_rules_keep_the_rest() -> None:
    r = rules(exclude_title_patterns=[r"^webinar"])
    assert not is_relevant(r, title="Webinar: intro", url="u")
    assert is_relevant(r, title="Introducing a model", url="u")


def test_title_and_url_patterns() -> None:
    r = rules(include_title_patterns=["copilot"], exclude_url_patterns=["/archive/"])
    assert is_relevant(r, title="GitHub Copilot update", url="https://x.test/new")
    assert not is_relevant(r, title="Unrelated change", url="https://x.test/new")
    assert not is_relevant(r, title="Copilot update", url="https://x.test/archive/1")


def test_any_include_rule_is_enough() -> None:
    r = rules(include_categories=["AI"], include_url_patterns=["/models/"])
    assert is_relevant(r, title="t", url="https://x.test/models/a", categories=[])
    assert is_relevant(r, title="t", url="https://x.test/blog", categories=["ai"])
    assert not is_relevant(r, title="t", url="https://x.test/blog", categories=["Search"])
