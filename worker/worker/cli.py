"""Command line tools for source configuration.

    python -m worker.cli validate-config [--config-dir DIR]
    python -m worker.cli verify-sources  [--config-dir DIR] [--slug SLUG ...] [--include-disabled]
    python -m worker.cli sync-config     [--config-dir DIR]

`validate-config` and `verify-sources` need no database. `sync-config` uses DATABASE_URL
(the worker role) and never deletes data.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from worker.sources.loader import LoadedConfig, validate_config_dir
from worker.sources.schema import INGESTIBLE_KINDS, SourceConfig
from worker.sources.verify import VerificationReport, make_client, verify_source

DEFAULT_CONFIG_DIR = Path("/config")


def _load(config_dir: Path) -> LoadedConfig | None:
    config, errors = validate_config_dir(config_dir)
    if config is None:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"{len(errors)} configuration error(s)")
    return config


def cmd_validate(args: argparse.Namespace) -> int:
    config = _load(args.config_dir)
    if config is None:
        return 1
    sources = [s for c in config.companies for s in c.sources]
    enabled = sum(1 for s in sources if s.enabled)
    print(
        f"config OK: {len(config.categories)} categories, {len(config.companies)} companies, "
        f"{len(sources)} sources ({enabled} enabled, {len(sources) - enabled} disabled)"
    )
    return 0


def _print_report(report: VerificationReport, source: SourceConfig) -> None:
    state = "enabled" if source.enabled else "DISABLED"
    print(f"\n[{report.verdict.upper()}] {source.slug} ({state})")
    print(f"  {report.url}")
    print(f"  HTTP {report.http_status}  {report.content_type}")
    stats = report.stats
    if stats:
        newest = f"{stats.newest:%Y-%m-%d}" if stats.newest else "n/a"
        oldest = f"{stats.oldest:%Y-%m-%d}" if stats.oldest else "n/a"
        print(
            f"  entries={stats.entries} title={stats.with_title} link={stats.with_link} "
            f"date={stats.with_date} description={stats.with_summary} "
            f"dates={oldest}..{newest}"
        )
        print(
            f"  relevance rules: keep={stats.kept_by_rules} filter={stats.filtered_by_rules}; "
            f"hosts={stats.link_hosts}"
        )
    for problem in report.problems:
        print(f"  PROBLEM: {problem}")
    for warning in report.warnings:
        print(f"  warning: {warning}")


def cmd_verify(args: argparse.Namespace) -> int:
    config = _load(args.config_dir)
    if config is None:
        return 1
    selected = 0
    failed = 0
    with make_client() as client:
        for company in config.companies:
            for source in company.sources:
                if args.slug and source.slug not in args.slug:
                    continue
                if source.kind not in INGESTIBLE_KINDS:
                    continue
                if not source.enabled and not (args.include_disabled or args.slug):
                    continue
                selected += 1
                report = verify_source(client, source, company.domains())
                _print_report(report, source)
                if report.verdict == "fail" and source.enabled:
                    failed += 1
    print(f"\nverified {selected} source(s); {failed} enabled source(s) failed")
    return 1 if failed or selected == 0 else 0


async def _sync(config: LoadedConfig) -> int:
    from sqlalchemy.ext.asyncio import create_async_engine

    from worker.config import get_settings
    from worker.sources.sync import sync_config

    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.begin() as conn:  # one transaction: all or nothing
            summary = await sync_config(conn, config)
    finally:
        await engine.dispose()
    for line in summary.lines():
        print(line)
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    config = _load(args.config_dir)
    if config is None:
        return 1
    return asyncio.run(_sync(config))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m worker.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, func, help_text in (
        ("validate-config", cmd_validate, "validate config/ (no network, no database)"),
        ("verify-sources", cmd_verify, "fetch feeds and inspect their real content"),
        ("sync-config", cmd_sync, "idempotently load config into the database"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
        p.set_defaults(func=func)
        if name == "verify-sources":
            p.add_argument("--slug", action="append", help="only this source slug (repeatable)")
            p.add_argument("--include-disabled", action="store_true")

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
