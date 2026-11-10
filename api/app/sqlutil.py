import math
from typing import Annotated

from fastapi import Query

Slug = Annotated[str, Query(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)]
SearchText = Annotated[str, Query(min_length=1, max_length=100)]
PageNumber = Annotated[int, Query(ge=1, le=100000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def like_pattern(value: str) -> str:
    """Escape LIKE wildcards so user text is matched literally (used with ESCAPE '\\')."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def page_count(total: int, page_size: int) -> int:
    return math.ceil(total / page_size) if total else 0
