"""Publication date handling.

Rules:
- Dates are converted to UTC for storage.
- A value that is only a date (no time) is stored as that date at 00:00 UTC with precision
  'day'. We never invent a time of day.
- A value with a time keeps precision 'datetime'. Values without a UTC offset are treated as
  UTC (the usual convention for feeds that omit it).
- Missing or unparseable values give (None, None). The discovery time is never used.
"""

import calendar
import datetime as dt
import re
import time
from email.utils import parsedate_to_datetime
from typing import Literal

Precision = Literal["day", "datetime"]

_ISO_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# RFC 822 style without a time, e.g. "Mon, 02 Nov 2026" or "02 Nov 2026"
_RFC_DATE_ONLY = re.compile(r"^(?:[A-Za-z]{3},\s*)?\d{1,2}\s+[A-Za-z]{3}\s+\d{4}$")


def _to_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)


def parse_entry_date(
    raw: str | None, parsed: time.struct_time | None = None
) -> tuple[dt.datetime | None, Precision | None]:
    """Parse a feed date. `raw` is the original string; `parsed` is feedparser's UTC fallback."""
    text = (raw or "").strip()
    if text:
        try:
            if _ISO_DATE_ONLY.match(text):
                day = dt.date.fromisoformat(text)
                return dt.datetime(day.year, day.month, day.day, tzinfo=dt.UTC), "day"
            if _RFC_DATE_ONLY.match(text):
                day = parsedate_to_datetime(text + " 00:00:00 +0000").date()
                return dt.datetime(day.year, day.month, day.day, tzinfo=dt.UTC), "day"
        except (ValueError, TypeError, IndexError):
            return None, None
        try:
            return _to_utc(dt.datetime.fromisoformat(text)), "datetime"
        except ValueError:
            pass
        try:
            return _to_utc(parsedate_to_datetime(text)), "datetime"
        except (ValueError, TypeError, IndexError):
            pass
    if parsed is not None:
        try:
            return dt.datetime.fromtimestamp(calendar.timegm(parsed), dt.UTC), "datetime"
        except (ValueError, OverflowError, OSError):
            return None, None
    return None, None
