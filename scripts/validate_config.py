"""Validate everything under config/ (used by CI and developers).

Requires the worker's runtime dependencies:  pip install -r worker/requirements.txt
Checks schema, unique slugs and URLs, category references, source types, hosting and
verification values, polling intervals, and official-domain ownership of every source.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "worker"))

from worker.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["validate-config", "--config-dir", str(ROOT / "config")]))
