from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    """Create the engine lazily so importing the app never requires a database.

    Defence in depth on top of the read-only database role: every session is read-only and
    statements are limited to five seconds.
    """
    return create_async_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        connect_args={
            "server_settings": {
                "default_transaction_read_only": "on",
                "statement_timeout": "5000",
            }
        },
    )


async def get_connection() -> AsyncIterator[AsyncConnection]:
    """Request-scoped read connection (FastAPI dependency)."""
    async with get_engine().connect() as conn:
        yield conn


async def check_database() -> bool:
    """Return True if the database answers a trivial query. Never raises."""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
