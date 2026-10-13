"""Puntos 4 y 5 sin base de datos: monitor de avance/cancelación, archivos
temporales (borrado seguro y limpieza de huérfanos), subida incompleta y
códigos HTTP del endpoint de cancelación.
"""

import io
import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app
from app.shared.config import Settings, get_settings
from app.shared.db.database import get_db
from app.shared.exceptions import FileValidationError, IngestionCancelled
from app.modules.ingesta import monitor as monitor_module
from app.modules.ingesta import router as router_module
from app.modules.ingesta.monitor import ExecutionMonitor
from app.modules.ingesta.schemas import CancelResponse
from app.modules.ingesta.services import (
    IncompleteUploadError,
    cleanup_orphan_uploads,
    delete_stored_upload,
    handle_upload_stream,
    stored_upload_path,
)
from tests.conftest import CSV_COLUMNS

CSV_OK = (";".join(CSV_COLUMNS) + "\n"
          "20260505084058;-0.18;-78.46;3;28886;192;61;-90;-15;-9;1;33171;740;LTE;0;LTE;CONNECTED;IDLE\n").encode()
EXECUTION_ID = uuid.uuid4()


# --- Monitor: frecuencia limitada y cancelación cooperativa ----------------------


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def beats(monkeypatch):
    """Sustituye la escritura real: registra cada latido y devuelve la bandera
    de cancelación que se le indique."""
    state = {"written": [], "cancel": False}

    def fake_write(connection, execution_id, etapa, progreso):
        state["written"].append((etapa, progreso))
        return state["cancel"]

    monkeypatch.setattr(monitor_module, "write_heartbeat", fake_write)
    return state


class _Connection:
    def close(self):
        pass


def _monitor(clock, interval=5.0):
    return ExecutionMonitor(EXECUTION_ID, _Connection, interval, clock)


def test_stage_change_is_always_written(beats):
    clock = _Clock()
    monitor = _monitor(clock)
    for etapa in ("extract", "validate", "clean"):
        monitor.stage(etapa)
    assert beats["written"] == [("extract", 5), ("validate", 25), ("clean", 35)]


def test_load_progress_is_rate_limited_not_per_batch(beats):
    clock = _Clock()
    monitor = _monitor(clock, interval=5.0)
    monitor.stage("load")
    for sent in range(10, 101, 10):  # 10 lotes muy rápidos
        clock.now += 1.0
        monitor.load_progress(sent, 100)

    # 10 s de lotes con intervalo mínimo de 5 s: 2 escrituras, no 10.
    assert beats["written"] == [("load", 55), ("load", 75), ("load", 95)]


def test_cancel_flag_stops_the_pipeline_at_next_checkpoint(beats):
    monitor = _monitor(_Clock())
    monitor.stage("extract")
    beats["cancel"] = True
    with pytest.raises(IngestionCancelled):
        monitor.stage("validate")


def test_execution_no_longer_processing_also_stops_the_pipeline(beats):
    beats["cancel"] = None  # la ejecución ya fue cerrada desde fuera
    monitor = _monitor(_Clock())
    with pytest.raises(IngestionCancelled):
        monitor.stage("extract")


def test_failed_heartbeat_write_does_not_break_the_load(monkeypatch):
    def broken(*args):
        raise OperationalError("UPDATE", {}, Exception("connection reset"))

    monkeypatch.setattr(monitor_module, "write_heartbeat", broken)
    _monitor(_Clock()).stage("load")  # no lanza: el Load continúa


# --- Archivos temporales -----------------------------------------------------------


@pytest.fixture
def settings(tmp_path):
    return Settings(data_input_dir=tmp_path / "input", orphan_upload_max_age_hours=24)


def _touch(settings, name, age_hours=0.0):
    path = settings.resolved_data_input_dir() / name
    path.write_bytes(b"x")
    if age_hours:
        old = time.time() - age_hours * 3600
        os.utime(path, (old, old))
    return path


def _upload_name(original="sesion.csv"):
    return f"{uuid.uuid4()}_{original}"


def test_stored_upload_path_rejects_paths_outside_input_dir(settings):
    for name in ("../fuera.csv", "sub/dentro.csv", "C:/Windows/win.csv"):
        with pytest.raises(FileValidationError):
            stored_upload_path(settings, name)


def test_delete_only_touches_upload_files_inside_input_dir(settings, tmp_path):
    manual = _touch(settings, "Session_43_20260623_165825.csv")
    upload = _touch(settings, _upload_name())
    outside = tmp_path / f"{uuid.uuid4()}_fuera.csv"
    outside.write_bytes(b"x")

    assert delete_stored_upload(settings, manual.name, "prueba") is False
    assert delete_stored_upload(settings, f"../{outside.name}", "prueba") is False
    assert delete_stored_upload(settings, None, "prueba") is False
    assert delete_stored_upload(settings, upload.name, "prueba") is True

    assert manual.exists()
    assert outside.exists()
    assert not upload.exists()


class _Statuses:
    def __init__(self, statuses):
        self.statuses = statuses

    def statuses_by_stored_filename(self, names):
        return {name: self.statuses[name] for name in names if name in self.statuses}


def test_orphan_cleanup_rules(settings, caplog):
    manual = _touch(settings, "Session_5_20260505_084058.csv", age_hours=1000)
    finished = _touch(settings, _upload_name("terminada.csv"))
    processing = _touch(settings, _upload_name("en_proceso.csv"), age_hours=1000)
    old_orphan = _touch(settings, _upload_name("vieja.csv"), age_hours=25)
    recent_orphan = _touch(settings, _upload_name("reciente.csv"), age_hours=1)
    repository = _Statuses({finished.name: "failed", processing.name: "processing"})

    with caplog.at_level("INFO"):
        deleted = cleanup_orphan_uploads(repository, settings)

    assert sorted(deleted) == sorted([finished.name, old_orphan.name])
    for kept in (manual, processing, recent_orphan):
        assert kept.exists()
    # Cada borrado queda en el log con su motivo.
    assert f"'{finished.name}' (motivo: su ejecución ya terminó (failed))" in caplog.text
    assert f"'{old_orphan.name}' (motivo: subido hace más de 24 h y nunca procesado)" in caplog.text


def test_orphan_cleanup_can_be_disabled(tmp_path):
    settings = Settings(data_input_dir=tmp_path / "input", orphan_cleanup_enabled=False)
    old = _touch(settings, _upload_name(), age_hours=1000)
    assert cleanup_orphan_uploads(_Statuses({}), settings) == []
    assert old.exists()


# --- Subida incompleta -------------------------------------------------------------


def test_truncated_upload_is_rejected_and_partial_deleted(settings):
    with pytest.raises(IncompleteUploadError) as exc:
        handle_upload_stream(
            "sesion.csv", io.BytesIO(CSV_OK[:-20]), None, settings, declared_size=len(CSV_OK)
        )
    assert "El archivo no se subió correctamente" in str(exc.value)
    assert list(settings.resolved_data_input_dir().iterdir()) == []


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.modules.ingesta.repository import HandoverRepository

    monkeypatch.setattr(HandoverRepository, "find_active_execution_by_filename", lambda self, name: None)
    app.dependency_overrides[get_settings] = lambda: Settings(data_input_dir=tmp_path / "input")
    app.dependency_overrides[get_db] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_upload_reports_incomplete_upload_per_file(client):
    response = client.post(
        "/api/v1/ingestion/upload",
        files=[("files", ("a.csv", CSV_OK, "text/csv")), ("files", ("b.csv", CSV_OK, "text/csv"))],
        data={"declared_sizes": [str(len(CSV_OK)), str(len(CSV_OK) + 500)]},
    )
    assert response.status_code == 200
    ok_item, bad_item = response.json()
    assert ok_item["ok"] is True
    assert bad_item["ok"] is False
    assert bad_item["error_code"] == "subida_incompleta"
    assert "El archivo no se subió correctamente" in bad_item["error"]


# --- Endpoint de cancelación: códigos HTTP ----------------------------------------


def test_cancel_endpoint_http_codes(client, monkeypatch):
    execution_id = str(uuid.uuid4())
    outcomes = {
        "ok": CancelResponse(execution_id=execution_id, status="cancelling", message="Cancelación solicitada."),
        "missing": None,
    }
    current = {"key": "ok"}

    def fake_request(parsed_id, repository, settings):
        if current["key"] == "done":
            raise FileValidationError("La ejecución ya está completada: no se puede cancelar.")
        return outcomes[current["key"]]

    monkeypatch.setattr(router_module, "request_cancellation", fake_request)
    url = f"/api/v1/ingestion/cancel/{execution_id}"

    assert client.post(url).status_code == 202
    current["key"] = "missing"
    assert client.post(url).status_code == 404
    current["key"] = "done"
    response = client.post(url)
    assert response.status_code == 409
    assert "ya está completada" in response.json()["detail"]
    assert client.post("/api/v1/ingestion/cancel/no-es-uuid").status_code == 400
