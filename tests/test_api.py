from fastapi.testclient import TestClient

from crawler.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_missing_job_returns_404():
    with TestClient(app) as client:
        response = client.get("/crawl/missing-job")

        assert response.status_code == 404
