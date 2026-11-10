"""Wiring: build a fetcher from settings and run the recurring ingestion loop."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from worker.config import Settings
from worker.ingest.fetcher import FeedFetcher, FetchSettings
from worker.ingest.runner import IngestReport, run_sources

logger = logging.getLogger("modelradar.ingest")


@asynccontextmanager
async def make_fetcher(settings: Settings) -> AsyncIterator[FeedFetcher]:
    async with httpx.AsyncClient(follow_redirects=True, max_redirects=5) as client:
        yield FeedFetcher(
            client,
            FetchSettings(
                timeout_seconds=settings.http_timeout_seconds,
                max_attempts=settings.http_max_attempts,
                backoff_base_seconds=settings.http_backoff_base_seconds,
                domain_min_interval_seconds=settings.http_domain_min_interval_seconds,
            ),
        )


def log_report(report: IngestReport) -> None:
    logger.info(
        "%s [%s] %s found=%d inserted=%d updated=%d filtered=%d invalid=%d%s",
        report.company,
        report.url,
        report.outcome,
        report.found,
        report.store.inserted,
        report.store.updated,
        report.filtered,
        report.invalid,
        f" error={report.error}" if report.error else "",
    )


async def ingestion_loop(engine: AsyncEngine, settings: Settings, stop: asyncio.Event) -> None:
    """Every tick, synchronise the sources whose poll interval has elapsed."""
    logger.info("ingestion loop started (tick=%ss)", settings.ingestion_tick_seconds)
    while not stop.is_set():
        try:
            async with make_fetcher(settings) as fetcher:
                for report in await run_sources(engine, fetcher, only_due=True):
                    log_report(report)
        except Exception:
            logger.exception("ingestion round failed; will retry next tick")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=settings.ingestion_tick_seconds)
    logger.info("ingestion loop stopped")
