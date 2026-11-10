from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_is_read_only() -> None:
    """Privacy/architecture guard: the public API exposes GET endpoints only."""
    allowed = {"GET", "HEAD", "OPTIONS"}
    for route in app.routes:
        if isinstance(route, APIRoute):
            assert route.methods <= allowed, f"{route.path} exposes {route.methods}"
