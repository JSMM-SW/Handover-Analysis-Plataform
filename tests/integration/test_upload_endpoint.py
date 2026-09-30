import pytest
from fastapi.testclient import TestClient

from app.shared.config import Settings, get_settings
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


def test_upload_valid_xlsx_returns_sheet_info(client, sample_handover_xlsx_bytes):
    response = client.post(
        "/api/v1/ingestion/upload",
        files=[
            ("files", ("handover.xlsx", sample_handover_xlsx_bytes, "application/vnd.ms-excel"))
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    item = body[0]
    assert item["ok"] is True
    assert item["original_filename"] == "handover.xlsx"
    assert item["upload"]["status"] == "uploaded"
    assert item["upload"]["sheets"][0]["name"] == "Datos 1"
    assert "upload_id" in item["upload"]
    assert "stored_filename" in item["upload"]


def test_upload_rejects_missing_required_columns(client, sample_xlsx_bytes):
    response = client.post(
        "/api/v1/ingestion/upload",
        files=[("files", ("handover.xlsx", sample_xlsx_bytes, "application/vnd.ms-excel"))],
    )

    assert response.status_code == 200
    item = response.json()[0]
    assert item["ok"] is False
    assert "estructura esperada" in item["error"]


def test_upload_rejects_non_xlsx_extension(client):
    response = client.post(
        "/api/v1/ingestion/upload",
        files=[("files", ("handover.csv", b"a,b,c", "text/csv"))],
    )

    assert response.status_code == 200
    item = response.json()[0]
    assert item["ok"] is False
    assert "no soportada" in item["error"]


def test_upload_rejects_corrupt_xlsx(client):
    response = client.post(
        "/api/v1/ingestion/upload",
        files=[("files", ("handover.xlsx", b"contenido invalido", "application/vnd.ms-excel"))],
    )

    assert response.status_code == 200
    item = response.json()[0]
    assert item["ok"] is False


def test_upload_multiple_files_are_processed_independently(
    client, sample_handover_xlsx_bytes, sample_xlsx_bytes
):
    """Un archivo inválido en el lote no debe impedir que los demás se
    procesen (punto 7: cada archivo es independiente)."""
    response = client.post(
        "/api/v1/ingestion/upload",
        files=[
            ("files", ("bueno.xlsx", sample_handover_xlsx_bytes, "application/vnd.ms-excel")),
            ("files", ("malo.xlsx", sample_xlsx_bytes, "application/vnd.ms-excel")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2

    good_item = next(item for item in body if item["original_filename"] == "bueno.xlsx")
    bad_item = next(item for item in body if item["original_filename"] == "malo.xlsx")

    assert good_item["ok"] is True
    assert good_item["upload"]["status"] == "uploaded"

    assert bad_item["ok"] is False
    assert "estructura esperada" in bad_item["error"]


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
