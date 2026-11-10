import datetime as dt

from tests.feeds import atom, atom_entry, rss, rss_item
from worker.ingest.entries import (
    announcement_url_key,
    compute_content_hash,
    html_to_text,
    parse_feed,
)
from worker.sources.schema import RelevanceRules

UTC = dt.UTC


def test_rss_entry_is_parsed_exactly() -> None:
    feed = rss(rss_item(title="Introducing Foo 1.0", link="https://acme.test/Posts/Foo-1"))
    result = parse_feed(feed, None)
    assert result.recognised and result.found == 1
    entry = result.entries[0]
    assert entry.title == "Introducing Foo 1.0"
    assert entry.url == "https://acme.test/Posts/Foo-1"  # case preserved
    assert entry.description == "A short description."
    assert entry.published_at == dt.datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
    assert entry.published_precision == "datetime"
    assert len(entry.content_hash) == 64


def test_atom_entry_is_parsed() -> None:
    result = parse_feed(atom(atom_entry(published="2026-10-31T08:00:00+01:00")), None)
    entry = result.entries[0]
    assert (entry.title, entry.url) == ("Atom post", "https://acme.test/atom/1")
    assert entry.description == "Atom summary"
    assert entry.published_at == dt.datetime(2026, 10, 31, 7, 0, tzinfo=UTC)  # published wins


def test_atom_uses_updated_when_there_is_no_published() -> None:
    entry = parse_feed(atom(atom_entry()), None).entries[0]
    assert entry.published_at == dt.datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def test_missing_title_or_url_is_skipped_and_counted() -> None:
    feed = rss(
        rss_item(title=None, link="https://acme.test/a"),
        rss_item(title="No link", link=None),
        rss_item(title="   ", link="https://acme.test/b"),
        rss_item(title="Good", link="https://acme.test/c"),
    )
    result = parse_feed(feed, None)
    assert (result.found, result.invalid) == (4, 3)
    assert [e.title for e in result.entries] == ["Good"]


def test_non_http_urls_are_rejected() -> None:
    feed = rss(
        rss_item(link="javascript:alert(1)"),
        rss_item(link="mailto:a@b.test"),
        rss_item(link="ftp://acme.test/x"),
    )
    result = parse_feed(feed, None)
    assert result.invalid == 3 and result.entries == []


def test_missing_date_is_none_and_entry_is_kept() -> None:
    entry = parse_feed(rss(rss_item(date=None)), None).entries[0]
    assert entry.published_at is None and entry.published_precision is None


def test_invalid_date_is_none_and_entry_is_kept() -> None:
    entry = parse_feed(rss(rss_item(date="sometime last week")), None).entries[0]
    assert entry.published_at is None and entry.published_precision is None
    assert entry.title == "Hello world"


def test_date_only_precision_is_preserved() -> None:
    entry = parse_feed(atom(atom_entry(updated="2026-11-06")), None).entries[0]
    assert entry.published_at == dt.datetime(2026, 11, 6, tzinfo=UTC)
    assert entry.published_precision == "day"


def test_missing_description_is_none() -> None:
    entry = parse_feed(rss(rss_item(desc=None)), None).entries[0]
    assert entry.description is None


def test_html_description_becomes_plain_text_without_inventing_content() -> None:
    html = (
        "&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt; &amp;amp; friends&lt;/p&gt;"
        "&lt;ul&gt;&lt;li&gt;one&lt;/li&gt;&lt;li&gt;two&lt;/li&gt;&lt;/ul&gt;"
    )
    entry = parse_feed(rss(rss_item(desc=html)), None).entries[0]
    assert entry.description == "Hello world & friends one two"


def test_html_to_text_removes_scripts_and_collapses_whitespace() -> None:
    assert html_to_text("<div>a\n\n  b<script>evil()</script></div>") == "a b"


def test_title_whitespace_is_trimmed_but_content_is_untouched() -> None:
    entry = parse_feed(rss(rss_item(title="  GPT‑X: a  big   launch ")), None).entries[0]
    assert entry.title == "GPT‑X: a  big   launch"  # non-ASCII hyphen and inner spaces kept


def test_feed_categories_are_kept_as_metadata() -> None:
    entry = parse_feed(rss(rss_item(cats=("Product", "Research"))), None).entries[0]
    assert entry.metadata == {"feed_categories": ["Product", "Research"]}
    assert parse_feed(rss(rss_item()), None).entries[0].metadata is None


def test_relevance_rules_filter_entries() -> None:
    feed = rss(
        rss_item(link="https://acme.test/1", cats=("Product",)),
        rss_item(link="https://acme.test/2", cats=("Story",)),
        rss_item(link="https://acme.test/3"),
    )
    rules = RelevanceRules(include_categories=["Product"])
    result = parse_feed(feed, rules)
    assert (result.found, result.filtered, len(result.entries)) == (3, 2, 1)
    assert result.entries[0].url == "https://acme.test/1"


def test_duplicates_inside_one_feed_are_collapsed() -> None:
    feed = rss(rss_item(link="https://acme.test/x"), rss_item(link="https://ACME.test/x/"))
    result = parse_feed(feed, None)
    assert len(result.entries) == 1 and result.duplicates_in_feed == 1


def test_fragments_distinguish_entries() -> None:
    feed = rss(
        rss_item(title="Note A", link="https://acme.test/notes#a"),
        rss_item(title="Note B", link="https://acme.test/notes#b"),
    )
    assert len(parse_feed(feed, None).entries) == 2


def test_content_hash_depends_on_title_url_and_description_only() -> None:
    base = compute_content_hash("t", "https://x.test/a", "d")
    assert base == compute_content_hash("t", "https://x.test/a", "d")
    assert base != compute_content_hash("t2", "https://x.test/a", "d")
    assert base != compute_content_hash("t", "https://x.test/a", "d2")
    assert base != compute_content_hash("t", "https://x.test/a", None)
    first = parse_feed(rss(rss_item(date="Mon, 02 Nov 2026 10:00:00 GMT")), None).entries[0]
    later = parse_feed(rss(rss_item(date="Tue, 03 Nov 2026 10:00:00 GMT")), None).entries[0]
    assert first.content_hash == later.content_hash  # a changed date alone is not a content change


def test_url_key_normalisation_does_not_alter_urls() -> None:
    assert announcement_url_key("HTTPS://Acme.TEST/a/") == announcement_url_key(
        "https://acme.test/a"
    )
    assert announcement_url_key("https://acme.test/a#x") != announcement_url_key(
        "https://acme.test/a#y"
    )
    assert announcement_url_key("https://acme.test/a?p=1") != announcement_url_key(
        "https://acme.test/a"
    )


def test_html_page_is_not_a_feed() -> None:
    result = parse_feed(b"<html><body>hello</body></html>", None)
    assert not result.recognised and result.entries == []


def test_empty_but_valid_feed_is_recognised() -> None:
    result = parse_feed(rss(), None)
    assert result.recognised and result.found == 0
