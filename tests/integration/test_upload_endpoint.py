import pytest
from fastapi.testclient import TestClient

from app.shared.config import Settings, get_settings
from app.shared.db.database import get_db
from app.main import app


class _EmptyDatabaseSession:
    """Sesión de base de datos falsa: cualquier consulta devuelve "sin
    resultados". /upload consulta si el archivo ya fue cargado
    (find_active_execution_by_filename); con esta sesión la respuesta es
    siempre "sin duplicados" y estos tests no necesitan una base real (el CI
    no tiene Postgres ni credenciales de Supabase). El rechazo por duplicado
    se prueba en tests/unit/test_duplicados.py y, contra Postgres, en
    tests/integration/test_duplicados_y_sesion.py."""

    def query(self, *args, **kwargs):
        return self

    filter = order_by = query

    def first(self):
        return None


def _override_get_db():
    yield _EmptyDatabaseSession()


@pytest.fixture
def invalid_csv_bytes():
    return b"foo;bar\n1;2\n"


@pytest.fixture
def client(tmp_path):
    def override_settings() -> Settings:
        return Settings(
            max_upload_size_mb=1,
            allowed_extensions=".csv",
            data_input_dir=tmp_path / "input",
        )

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_upload_valid_csv_returns_sheet_info(client, sample_handover_csv_bytes):
    response = client.post(
        "/api/v1/ingestion/upload",
        files=[
            ("files", ("handover.csv", sample_handover_csv_bytes, "text/csv"))
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    item = body[0]
    assert item["ok"] is True
    assert item["original_filename"] == "handover.csv"
    assert item["upload"]["status"] == "uploaded"
    assert item["upload"]["sheets"][0]["name"].endswith("_handover")
    assert "upload_id" in item["upload"]
    assert "stored_filename" in item["upload"]


def test_upload_rejects_missing_required_columns(client, invalid_csv_bytes):
    response = client.post(
        "/api/v1/ingestion/upload",
        files=[("files", ("handover.csv", invalid_csv_bytes, "text/csv"))],
    )

    assert response.status_code == 200
    item = response.json()[0]
    assert item["ok"] is False
    assert "estructura esperada" in item["error"]


def test_upload_rejects_non_csv_extension(client):
    response = client.post(
        "/api/v1/ingestion/upload",
        files=[("files", ("handover.xlsx", b"a,b,c", "text/csv"))],
    )

    assert response.status_code == 200
    item = response.json()[0]
    assert item["ok"] is False
    assert "no soportada" in item["error"]


def test_upload_rejects_corrupt_xlsx(client):
    response = client.post(
        "/api/v1/ingestion/upload",
        files=[("files", ("handover.xlsx", b"contenido invalido", "text/csv"))],
    )

    assert response.status_code == 200
    item = response.json()[0]
    assert item["ok"] is False


def test_upload_multiple_files_are_processed_independently(
    client, sample_handover_csv_bytes, invalid_csv_bytes
):
    """Un archivo inválido en el lote no debe impedir que los demás se
    procesen (punto 7: cada archivo es independiente)."""
    response = client.post(
        "/api/v1/ingestion/upload",
        files=[
            ("files", ("bueno.csv", sample_handover_csv_bytes, "text/csv")),
            ("files", ("malo.csv", invalid_csv_bytes, "text/csv")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2

    good_item = next(item for item in body if item["original_filename"] == "bueno.csv")
    bad_item = next(item for item in body if item["original_filename"] == "malo.csv")

    assert good_item["ok"] is True
    assert good_item["upload"]["status"] == "uploaded"

    assert bad_item["ok"] is False
    assert "estructura esperada" in bad_item["error"]


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
