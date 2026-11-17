# Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Foundations: monorepo, Docker Compose, env/credentials, privacy defaults, CI, docs | Done |
| 1A | Database schema and Alembic migrations, role permissions, migration tests | Done |
| 1B | Official source configuration (first batch of 10), validation, feed verification, relevance rules, config sync | Done |
| 2 | RSS/Atom ingestion: conditional fetching, retries, robots.txt, duplicate prevention, run history, scheduler | Done |
| 3 | Read-only API and web frontend: Dashboard, Models, Categories, Companies, Sources, About | Done |
| 4 | Run the full stack with real data, fix issues found, update docs | In progress |
| 5 | Rule-based classification: announcement kind and categories | Not started |
| 6 | Model detection: model names, versions, first-announced dates | Not started |
| 7 | More official RSS/Atom sources (batch 1) | Not started |
| 8 | Official GitHub and Hugging Face sources | Not started |
| 9 | HTML extraction in small gated batches (about 5-8 sources each) | Not started |
| 10 | Frontend polish: Models, Categories, Dashboard, "new" indicator from publication date | Not started |
| 11 | Hardening: source-drift visibility, caching, performance, full browser tests | Not started |
| 12 | Deployment: hosting, HTTPS, backups | Not started |

Work proceeds one phase at a time and waits for approval between phases.
