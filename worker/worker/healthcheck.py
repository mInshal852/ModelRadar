"""Container healthcheck: exits 0 only if the worker heartbeat is recent."""

import sys

from worker.config import get_settings
from worker.heartbeat import heartbeat_age_seconds

if __name__ == "__main__":
    settings = get_settings()
    age = heartbeat_age_seconds(settings.heartbeat_file)
    limit = settings.heartbeat_interval_seconds * 3
    sys.exit(0 if age is not None and age < limit else 1)
