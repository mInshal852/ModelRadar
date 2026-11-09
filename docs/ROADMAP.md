# Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Foundations: monorepo, Docker Compose, env/credentials, privacy defaults, CI, docs | Implemented; pending approval |
| 1A | Database schema and Alembic migrations, role permissions, migration tests | Implemented on `feature/database-schema`; pending review |
| 1B+ | YAML loader, feed (RSS/Atom) pipeline, rule-based classification and relevance filters, scheduler. Feed rollout in gated sub-batches | Not started |
| 2 | Models: per-company model-name patterns, versions, first-announced dates | Not started |
| 3 | Public UI: Dashboard, Models, Categories, Companies, Sources, About. Playwright tests | Not started |
| 4 | HTML extraction in small gated batches (about 5-8 sources each) | Not started |
| 5 | Hardening: source-drift visibility, caching, documentation. Production deployment decided later | Not started |

Work proceeds one phase at a time and waits for approval between phases.
