# config/

Version-controlled configuration. There is no admin UI: changes are made by pull request.

| Path | Purpose | Status |
|---|---|---|
| `categories.yaml` | The approved 17-category taxonomy | Present (Phase 0) |
| `companies/<slug>.yaml` | One file per company: name, website, categories, and its official sources | Added in Phase 1 |

This directory contains configuration only. It never contains announcements, and the
database is never seeded with announcement data.

Validate the configuration with:

```bash
python scripts/validate_config.py
```
