from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    """Create the engine lazily so importing the app never requires a database."""
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


async def check_database() -> bool:
    """Return True if the database answers a trivial query. Never raises."""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
