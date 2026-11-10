"""ModelRadar sync worker.

Phase 0: foundation only. The worker connects to the database with its own
role and keeps a heartbeat. Fetching, extraction and classification are added
in Phase 1 and later; nothing here collects or stores announcements yet.
"""

import asyncio
import contextlib
import logging
import signal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from worker.config import get_settings
from worker.heartbeat import write_heartbeat

logger = logging.getLogger("modelradar.worker")


async def run() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    logger.info("worker started (environment=%s)", settings.environment)
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
