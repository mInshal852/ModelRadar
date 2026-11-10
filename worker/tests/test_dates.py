import datetime as dt
import time

import pytest

from worker.ingest.dates import parse_entry_date

UTC = dt.UTC


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Mon, 02 Nov 2026 10:00:00 GMT", dt.datetime(2026, 11, 2, 10, 0, tzinfo=UTC)),
        ("Mon, 02 Nov 2026 10:00:00 +0100", dt.datetime(2026, 11, 2, 9, 0, tzinfo=UTC)),
        ("Mon, 02 Nov 2026 10:00:00 -0500", dt.datetime(2026, 11, 2, 15, 0, tzinfo=UTC)),
        ("2026-11-01T12:00:00Z", dt.datetime(2026, 11, 1, 12, 0, tzinfo=UTC)),
        ("2026-11-01T12:00:00+02:00", dt.datetime(2026, 11, 1, 10, 0, tzinfo=UTC)),
        ("2026-11-06T00:00:00-08:00", dt.datetime(2026, 11, 6, 8, 0, tzinfo=UTC)),
        ("2026-11-01T12:00:00", dt.datetime(2026, 11, 1, 12, 0, tzinfo=UTC)),  # no offset: UTC
    ],
)
def test_datetimes_are_converted_to_utc(raw: str, expected: dt.datetime) -> None:
    value, precision = parse_entry_date(raw)
    assert value == expected
    assert value is not None and value.utcoffset() == dt.timedelta(0)
    assert precision == "datetime"


@pytest.mark.parametrize("raw", ["2026-11-06", "Fri, 06 Nov 2026", "06 Nov 2026"])
def test_date_only_values_keep_day_precision(raw: str) -> None:
    value, precision = parse_entry_date(raw)
    assert value == dt.datetime(2026, 11, 6, tzinfo=UTC)
    assert precision == "day"


def test_explicit_midnight_time_is_not_treated_as_date_only() -> None:
    # A feed that states a time keeps datetime precision (no guessing).
    value, precision = parse_entry_date("Thu, 29 Oct 2026 00:00:00 GMT")
    assert (value, precision) == (dt.datetime(2026, 10, 29, tzinfo=UTC), "datetime")


@pytest.mark.parametrize("raw", [None, "", "   ", "not a date", "2026-13-45", "Foo, 99 Zzz 2026"])
def test_missing_or_invalid_dates_give_none(raw: str | None) -> None:
    assert parse_entry_date(raw) == (None, None)


def test_falls_back_to_feedparser_value_when_raw_is_unusable() -> None:
    parsed = time.struct_time((2026, 11, 2, 10, 0, 0, 0, 0, 0))
    value, precision = parse_entry_date("garbled", parsed)
    assert (value, precision) == (dt.datetime(2026, 11, 2, 10, 0, tzinfo=UTC), "datetime")


def test_never_uses_the_current_time() -> None:
    assert parse_entry_date(None, None) == (None, None)
