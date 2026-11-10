from fastapi import FastAPI, Response

from app.db import check_database

# Public, read-only API. There is intentionally no authentication, no user
# model and no write endpoint: ModelRadar only serves public information.
app = FastAPI(
    title="ModelRadar API",
    version="0.1.0",
    description="Read-only API for publicly available AI announcements.",
    redoc_url=None,
)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Liveness probe. Does not touch the database."""
    return {"status": "ok"}


@app.get("/health/db", tags=["health"])
async def health_db(response: Response) -> dict[str, str]:
    """Readiness probe: verifies the database connection."""
    if await check_database():
        return {"status": "ok"}
    response.status_code = 503
    return {"status": "unavailable"}
