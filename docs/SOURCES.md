# Official sources: configuration, verification and sync

ModelRadar collects only from **official** company sources. Which companies and sources exist
is defined by YAML files in `config/`, reviewed through pull requests. There is no admin UI.

> Phase 1B covers configuration, verification and loading config into the database. It does
> **not** fetch announcements for storage, schedule polling or classify anything. No
> announcements exist in the database.

## Files

| Path | Purpose |
|---|---|
| `config/categories.yaml` | The 17 approved top-level categories and their children |
| `config/companies/<slug>.yaml` | One file per company, including its sources. The file name must equal the company `slug` |

Code: `worker/worker/sources/` (`schema.py`, `loader.py`, `relevance.py`, `verify.py`, `sync.py`)
and the command line in `worker/worker/cli.py`.

## Company file

```yaml
slug: acme-ai                  # lowercase letters, digits, hyphens; unique; equals the file name
name: Acme AI
website_url: https://acme.example
country: US                    # optional, ISO 3166-1 alpha-2; omit if unsure
description: ...               # optional
official_domains: [acme.dev]   # optional extra domains the company officially owns
categories: [language-reasoning, code-software]   # slugs from categories.yaml (parents or children)
sources:
  - ...
```

## Source entry

| Field | Required | Meaning |
|---|---|---|
| `slug` | yes | Unique across all companies. Identifies the source inside the config |
| `name` | yes | Human-readable name |
| `kind` | yes | `rss`, `atom`, `github`, `api`, `sitemap`, `html`, `manual` |
| `url` | yes | Exact URL (http/https, no credentials). Unique across all sources |
| `hosting` | yes | `first_party` or `official_third_party` (third-party needs `hosting_notes`) |
| `hosting_notes` | for third-party | Explain who hosts it and why it is official |
| `content_scope` | yes | `dedicated_ai` or `mixed` (mixed feeds should have `relevance_rules`) |
| `verification_level` | no (default `http_only`) | `http_only`, `content_sampled`, `content_verified` |
| `verified_at` | when level is above `http_only` | Date you inspected the content |
| `verification_notes` | yes | What you actually saw (see below) |
| `poll_interval_minutes` | yes | 15 to 10080. Used by the later scheduler |
| `enabled` / `disabled_reason` | no (default enabled) | A disabled source needs a reason |
| `relevance_rules` | no | See "Relevance rules" |
| `extractor_config` | HTML sources only | Reserved for the later HTML phase; not allowed on RSS/Atom |

Rules enforced by validation:

- **Official domains:** a source's host must equal, or be a subdomain of, the company's
  `website_url` domain or one of its `official_domains`. Add an `official_domains` entry only for
  domains the company really owns (for example `claude.com` for Anthropic's platform docs).
- **Only feeds can be enabled now.** `github`, `api`, `sitemap`, `html` and `manual` sources may
  be listed, but must be `enabled: false` until their ingestion exists.
- Unique company slugs, source slugs and source URLs (URLs are compared ignoring case of the
  host, fragments and trailing slashes); every category must exist.

## How verification works

HTTP 200 is **not** enough. For RSS/Atom sources run:

```bash
docker compose run --rm worker python -m worker.cli verify-sources
```

Options: `--slug SLUG` (repeatable), `--include-disabled`, `--config-dir DIR`. The command
fetches each feed (identifying User-Agent, robots.txt respected, no retries or workarounds) and
inspects what is really inside:

- entries, and how many have a title, link, publication date and description;
- date range and age of the newest entry;
- link hosts, and how many links leave the company's official domains;
- feed category tags, and how many entries the relevance rules would keep or drop;
- duplicate links.

Verdicts: `pass`, `pass_with_warnings` (for example some entries lack a description or date, or
the newest entry is over 180 days old) and `fail` (HTTP error, not a feed, no entries, most
entries missing a title or link, mostly off-domain links, newest entry over 365 days old, rules
removing everything, blocked by robots.txt). Missing dates and descriptions are never invented;
they stay `NULL`. A blocked source (403, robots.txt, CAPTCHA) is reported and never bypassed.

The command exits non-zero if an **enabled** source fails.

After you read real entries, record the result honestly in `verification_notes` and set
`verification_level: content_sampled` (some entries read) with `verified_at`. Use
`content_verified` only after a thorough review of the content.

## Adding a new official source

1. Find the feed on the company's own site (look for the page's RSS/Atom link). Do not guess
   URLs and do not use third-party aggregators.
2. Add the company file (or add a source to an existing one) with `enabled: true` only if it
   passes verification; otherwise `enabled: false` with a `disabled_reason`.
3. Run `validate-config`, then `verify-sources --slug <new-slug>`; read some entries yourself.
4. Write `verification_notes` from what you saw (counts, date range, missing fields, tags,
   anything unusual) and set `content_scope`, `relevance_rules` and `poll_interval_minutes`.
5. Open a pull request. CI runs the validation.

## Relevance rules

For `mixed` feeds, `relevance_rules` decides which entries are kept:

```yaml
relevance_rules:
  include_categories: [Product, Research]   # feed's own tags, case-insensitive exact match
  exclude_categories: [Story]
  include_title_patterns: ['^Introducing']  # case-insensitive regular expressions
  exclude_title_patterns: ['webinar']
  include_url_patterns: ['/models/']
  exclude_url_patterns: ['/customers/']
```

- Exclusions always win.
- If any `include_*` list is non-empty, an entry must match at least one include rule (so
  untagged entries are dropped when `include_categories` is set).
- With no rules, everything is kept.
- Rules only keep or drop entries; they never classify or rewrite them.

Rules favour precision over recall; write the trade-off into `verification_notes`.

## Disabling an unreliable source

Set `enabled: false` and a `disabled_reason`, keep the verification notes, and run
`sync-config`. The database row is kept with status `disabled` and the reason is prefixed to its
`verification_notes`. To re-enable, set `enabled: true` (it must pass `verify-sources`); the
status returns to "never synced" (`NULL`).

## Validation and database sync

```bash
# Validate (no network, no database)
docker compose run --rm --no-deps worker python -m worker.cli validate-config
# or on the host, with the worker dependencies installed:
python scripts/validate_config.py

# Load config into the database (as the worker role; migrations must already be applied)
docker compose run --rm worker python -m worker.cli sync-config
```

`sync-config` runs in one transaction and is idempotent:

- creates missing categories, companies, company-category links and sources;
- updates config-owned fields (names, URLs, verification metadata, relevance rules, polling);
- never overwrites runtime fields (`etag`, `last_modified`, `last_synced_at`, `last_error`,
  `consecutive_failures`, and the status of enabled sources);
- never deletes anything. Database rows that are no longer in the config (companies, sources,
  category links) are kept and reported as warnings; remove them manually if intended;
- never writes announcements.

Companies are identified by `slug`, categories by `slug`, sources by (company, URL). The
database has no source slug column, so a source's `slug` exists only in the config. Changing a
source's URL therefore creates a new row and leaves the old one (reported as a warning).

## Current first batch

Ten official companies and eleven sources are configured; ten sources are enabled and one is
disabled. See `config/companies/` for each source's exact URL, hosting classification, scope,
verification notes and relevance rules.
