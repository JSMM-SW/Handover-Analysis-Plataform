"""Rechazo de archivos ya cargados (punto 1), sin base de datos: la consulta
al repositorio se sustituye por un doble. Los casos contra Postgres (índice
único parcial, subidas simultáneas) están en
tests/integration/test_duplicados_y_sesion.py.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.shared.config import Settings, get_settings
from app.shared.db.database import get_db
from app.shared.exceptions import DuplicateFileError
from app.shared.file_utils import filename_key
from app.modules.ingesta.repository import HandoverRepository
from app.modules.ingesta.schemas import ProcessRequest
from app.modules.ingesta.services import ensure_not_already_loaded, start_ingestion
from tests.conftest import CSV_COLUMNS

CSV_OK = (";".join(CSV_COLUMNS) + "\n"
          "20260505084058;-0.18;-78.46;3;28886;192;61;-90;-15;-9;1;33171;740;LTE;0;LTE;CONNECTED;IDLE\n").encode()

COMPLETED = SimpleNamespace(
    status="completed",
    sesion_label=44,
    processing_date=datetime(2026, 10, 7, 17, 42, tzinfo=timezone.utc),
)
PROCESSING = SimpleNamespace(
    status="processing",
    sesion_label=None,
    processing_date=datetime(2026, 10, 7, 17, 42, tzinfo=timezone.utc),
)


@pytest.mark.parametrize(
    "name",
    ["Session_44.csv", "SESSION_44.CSV", "  session_44.csv  ", "C:\\datos\\Session_44.csv", "carpeta/Session_44.csv"],
)
def test_filename_key_ignores_path_spaces_and_case(name):
    assert filename_key(name) == "session_44.csv"


def test_filename_key_distinguishes_different_files():
    assert filename_key("Session_44.csv") != filename_key("Session_45.csv")


class _Repo:
    def __init__(self, existing):
        self.existing = existing
        self.created = []

    def find_active_execution_by_filename(self, filename):
        return self.existing

    def create_execution(self, filename):
        self.created.append(filename)
        raise AssertionError("no debe crear una ejecución para un duplicado")


def test_completed_execution_blocks_with_session_and_local_date():
    repo, settings = _Repo(COMPLETED), Settings()
    with pytest.raises(DuplicateFileError) as exc:
        ensure_not_already_loaded("Session_44.csv", repo, settings)
    assert str(exc.value) == (
        "El archivo 'Session_44.csv' ya fue cargado como Sesión 44 el 07/10/2026 12:42. "
        "No se volvió a procesar."
    )


def test_processing_execution_blocks_with_clear_message():
    repo, settings = _Repo(PROCESSING), Settings()
    with pytest.raises(DuplicateFileError, match="ya se está procesando"):
        ensure_not_already_loaded("Session_44.csv", repo, settings)


def test_no_active_execution_allows_upload():
    # failed/cancelled no se devuelven como "activas": el nombre queda libre.
    ensure_not_already_loaded("Session_44.csv", _Repo(None), Settings())


def test_process_duplicate_does_not_create_execution_and_deletes_stored_file(tmp_path):
    settings = Settings(data_input_dir=tmp_path / "input")
    # Nombre como los que genera /upload (prefijo upload_id): solo esos se borran.
    stored = settings.resolved_data_input_dir() / "5db4d5d9-6ac0-4044-bda2-c6770c50a4c1_Session_44.csv"
    stored.write_bytes(CSV_OK)
    repo = _Repo(COMPLETED)
    payload = ProcessRequest(stored_filename=stored.name, original_filename="Session_44.csv")

    with pytest.raises(DuplicateFileError, match="Sesión 44"):
        start_ingestion(payload, settings, repo)
    assert repo.created == []
    assert not stored.exists()


@pytest.fixture
def client(tmp_path, monkeypatch):
    loaded = {"session_44.csv": COMPLETED}
    monkeypatch.setattr(
        HandoverRepository,
        "find_active_execution_by_filename",
        lambda self, filename: loaded.get(filename_key(filename)),
    )
    app.dependency_overrides[get_settings] = lambda: Settings(data_input_dir=tmp_path / "input")
    app.dependency_overrides[get_db] = lambda: None
    with TestClient(app) as test_client:
        yield test_client, tmp_path / "input"
    app.dependency_overrides.clear()


def _upload(client, *names):
    return client.post(
        "/api/v1/ingestion/upload",
        files=[("files", (name, CSV_OK, "text/csv")) for name in names],
    )


def test_upload_already_loaded_file_returns_409_and_saves_nothing(client):
    test_client, input_dir = client
    response = _upload(test_client, "SESSION_44.csv")

    assert response.status_code == 409
    [item] = response.json()
    assert item["ok"] is False
    assert item["error_code"] == "duplicado"
    assert "ya fue cargado como Sesión 44" in item["error"]
    assert not input_dir.exists() or not any(input_dir.iterdir())  # no se guardó nada


def test_upload_batch_reports_per_file_and_detects_repeated_names(client):
    test_client, _ = client
    response = _upload(test_client, "Session_50.csv", "session_50.CSV", "Session_44.csv")

    assert response.status_code == 200  # hay al menos un archivo aceptado
    first, repeated, loaded = response.json()
    assert first["ok"] is True
    assert first["error_code"] is None
    assert repeated["ok"] is False
    assert repeated["error_code"] == "duplicado_en_seleccion"
    assert loaded["ok"] is False
    assert loaded["error_code"] == "duplicado"


def test_upload_invalid_file_is_not_reported_as_duplicate(client):
    test_client, _ = client
    response = test_client.post(
        "/api/v1/ingestion/upload", files=[("files", ("otro.csv", b"foo;bar\n1;2\n", "text/csv"))]
    )
    assert response.status_code == 200
    assert response.json()[0]["error_code"] == "invalido"
