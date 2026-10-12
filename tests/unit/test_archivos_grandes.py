"""Punto 3 (archivos grandes), sin base de datos: subida en streaming con
tope de tamaño, lectura rápida del CSV equivalente a la anterior y
reintentos de la conexión inicial.
"""

import io

import pandas as pd
import pytest
from sqlalchemy.exc import OperationalError

from app.shared.config import Settings
from app.shared.exceptions import FileValidationError, SchemaValidationError
from app.modules.ingesta import services
from app.modules.ingesta.etl.extractor import _read_csv, detect_csv_encoding
from app.modules.ingesta.services import handle_upload_stream
from tests.conftest import CSV_COLUMNS

ROW = "20260505084058;-0.1571013166666666;-78.30784905;3;28886;192;61;-90;-15;-9;1;33171;740;LTE;0;LTE;CONNECTED;IDLE"
CSV_OK = (";".join(CSV_COLUMNS) + "\n" + ROW + "\n").encode()


@pytest.fixture
def settings(tmp_path):
    return Settings(max_upload_size_mb=1, data_input_dir=tmp_path / "input", upload_chunk_bytes=64 * 1024)


def _stored(settings):
    return list(settings.resolved_data_input_dir().iterdir())


def test_stream_upload_stores_file_and_reports_real_size(settings):
    response = handle_upload_stream("sesion.csv", io.BytesIO(CSV_OK), len(CSV_OK), settings)

    assert response.file_size_bytes == len(CSV_OK)
    [stored] = _stored(settings)
    assert stored.read_bytes() == CSV_OK


def test_oversized_upload_reports_received_and_maximum_size(settings):
    oversized = CSV_OK + b"x" * (2 * 1024 * 1024)
    with pytest.raises(FileValidationError) as exc:
        handle_upload_stream("sesion.csv", io.BytesIO(oversized), len(oversized), settings)

    assert "pesa 2.0 MB" in str(exc.value)
    assert "tamaño máximo permitido (1 MB)" in str(exc.value)
    assert _stored(settings) == []


def test_oversized_upload_without_declared_size_is_cut_and_partial_deleted(settings):
    oversized = CSV_OK + b"x" * (2 * 1024 * 1024)
    with pytest.raises(FileValidationError, match="supera el tamaño máximo permitido"):
        handle_upload_stream("sesion.csv", io.BytesIO(oversized), None, settings)
    assert _stored(settings) == []


def test_upload_with_invalid_structure_deletes_stored_file(settings):
    with pytest.raises(SchemaValidationError):
        handle_upload_stream("otro.csv", io.BytesIO(b"foo;bar\n1;2\n"), 12, settings)
    assert _stored(settings) == []


@pytest.mark.parametrize("delimiter", [";", ","])
def test_fast_csv_read_matches_previous_python_engine(tmp_path, delimiter):
    """Mismos tipos y mismos valores (incluido el último dígito de los
    decimales) que read_csv(sep=None, engine="python")."""
    path = tmp_path / "sesion.csv"
    rows = [ROW, ROW.replace("-0.1571013166666666", "-0.2101313166666666").replace(";192;", ";;")]
    text = "\n".join([";".join(CSV_COLUMNS), *rows]) + "\n"
    path.write_text(text.replace(";", delimiter), encoding="utf-8")

    fast = _read_csv(path, detect_csv_encoding(path))
    previous = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")

    pd.testing.assert_frame_equal(fast, previous, check_exact=True)


def test_csv_without_detectable_delimiter_uses_previous_reader(tmp_path):
    path = tmp_path / "una_columna.csv"
    path.write_text("sys_time\n20260505084058\n", encoding="utf-8")
    previous = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    pd.testing.assert_frame_equal(_read_csv(path, "utf-8-sig"), previous, check_exact=True)


class _Session:
    def __init__(self, fail: bool):
        self.fail, self.closed = fail, False

    def execute(self, *args, **kwargs):
        if self.fail:
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    def close(self):
        self.closed = True


def test_initial_connection_is_retried_with_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr(services.time, "sleep", sleeps.append)
    sessions = [_Session(fail=True), _Session(fail=True), _Session(fail=False)]
    remaining = iter(sessions)
    config = Settings(db_connect_retries=3, db_connect_retry_backoff_seconds=0.5)

    db, _ = services._open_repository(lambda: next(remaining), config, "exec")

    assert db is sessions[2]
    assert sleeps == [0.5, 1.0]
    assert sessions[0].closed
    assert sessions[1].closed


def test_initial_connection_gives_up_after_configured_retries(monkeypatch):
    monkeypatch.setattr(services.time, "sleep", lambda seconds: None)
    attempts = []

    def factory():
        attempts.append(1)
        return _Session(fail=True)

    config = Settings(db_connect_retries=2, db_connect_retry_backoff_seconds=0.1)
    with pytest.raises(OperationalError):
        services._open_repository(factory, config, "exec")
    assert len(attempts) == 3
