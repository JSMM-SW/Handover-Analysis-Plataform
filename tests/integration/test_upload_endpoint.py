import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app


@pytest.fixture
def client(tmp_path):
    def override_settings() -> Settings:
        return Settings(
            max_upload_size_mb=1,
            allowed_extensions=".xlsx",
            data_input_dir=tmp_path / "input",
        )

    app.dependency_overrides[get_settings] = override_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_upload_valid_xlsx_returns_sheet_info(client, sample_xlsx_bytes):
    response = client.post(
        "/api/v1/ingestion/upload",
        files={"file": ("handover.xlsx", sample_xlsx_bytes, "application/vnd.ms-excel")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["original_filename"] == "handover.xlsx"
    assert body["sheets"][0]["name"] == "Handover"
    assert "execution_id" in body


def test_upload_rejects_non_xlsx_extension(client):
    response = client.post(
        "/api/v1/ingestion/upload",
        files={"file": ("handover.csv", b"a,b,c", "text/csv")},
    )

    assert response.status_code == 400
    assert "no soportada" in response.json()["detail"]


def test_upload_rejects_corrupt_xlsx(client):
    response = client.post(
        "/api/v1/ingestion/upload",
        files={
            "file": (
                "handover.xlsx",
                b"contenido invalido",
                "application/vnd.ms-excel",
            )
        },
    )

    assert response.status_code == 422


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
