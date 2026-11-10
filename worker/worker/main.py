"""ModelRadar sync worker.

Keeps a heartbeat and, when enabled, runs the recurring RSS/Atom ingestion loop. Each source
is synchronised on its configured poll interval; overlapping runs are prevented per source.
"""

import asyncio
import contextlib
import logging
import signal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from worker.config import get_settings
from worker.heartbeat import write_heartbeat
from worker.ingest.service import ingestion_loop

logger = logging.getLogger("modelradar.worker")


async def run() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    logger.info(
        "worker started (environment=%s, ingestion=%s)",
        settings.environment,
        "on" if settings.ingestion_enabled else "off",
    )
    ingestion_task = (
        asyncio.create_task(ingestion_loop(engine, settings, stop))
        if settings.ingestion_enabled
        else None
    )
    try:
        while not stop.is_set():
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                write_heartbeat(settings.heartbeat_file)
            except Exception:
                logger.warning("database not reachable; will retry")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=settings.heartbeat_interval_seconds)
    finally:
        stop.set()
        if ingestion_task is not None:
            ingestion_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await ingestion_task
        await engine.dispose()
        logger.info("worker stopped")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
