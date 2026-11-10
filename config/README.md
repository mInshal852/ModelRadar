# config/

Version-controlled configuration. There is no admin UI: changes are made by pull request.

| Path | Purpose | Status |
|---|---|---|
| `categories.yaml` | The approved 17-category taxonomy | Present (Phase 0) |
| `companies/<slug>.yaml` | One file per company: name, website, categories, and its official sources | First batch present (Phase 1B) |

See [docs/SOURCES.md](../docs/SOURCES.md) for the file format, verification and how to add a source.

This directory contains configuration only. It never contains announcements, and the
database is never seeded with announcement data.

Validate the configuration with:

```bash
# needs: pip install -r worker/requirements.txt
python scripts/validate_config.py
```
