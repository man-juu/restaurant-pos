from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_reports_database_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_database_unavailable() -> None:
    settings = Settings.model_validate(
        {"environment": "test", "database_url": "postgresql+asyncpg://x:y@127.0.0.1:1/none"}
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
