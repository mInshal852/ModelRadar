import time
from pathlib import Path


def write_heartbeat(path: Path) -> None:
    """Record that the worker loop is alive (used by the container healthcheck)."""
    path.write_text(str(time.time()), encoding="ascii")


def heartbeat_age_seconds(path: Path) -> float | None:
    """Seconds since the last heartbeat, or None if there has not been one."""
    try:
        return time.time() - float(path.read_text(encoding="ascii"))
    except (FileNotFoundError, ValueError):
        return None
