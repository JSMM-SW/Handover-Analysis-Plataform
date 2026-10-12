"""Duplicados (punto 1) y numeración de sesiones (punto 2) contra Postgres.

Requieren la migración 010 (filename_clave, ux_etl_execution_filename_activo,
etl_sesion_contador y trg_etl_execution_sesion_label). Ningún test confirma
nada: cada conexión termina en rollback, así que no dejan filas ni consumen
números de sesión (lo verifica `counter_untouched`).

Nombres de archivo con un sufijo aleatorio: no chocan con sesiones reales ni
con las de otros integrantes que estén cargando archivos a la vez.
"""

import threading
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.shared.config import settings
from app.shared.exceptions import DuplicateFileError
from app.modules.ingesta.repository import HandoverRepository

from tests.integration.conftest import test_engine as engine  # noqa: E402


def _counter() -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT ultimo FROM etl_sesion_contador WHERE id = 1")).scalar()


@pytest.fixture(scope="module", autouse=True)
def counter_untouched():
    """Los tests de este módulo no consumen números de sesión."""
    before = _counter()
    yield
    assert _counter() == before


@pytest.fixture()
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def repository(db_session):
    return HandoverRepository(db_session)


def _name(prefix="Session_test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}.csv"


def _complete(repository, execution_id, errors=()):
    repository.finish_execution(
        execution_id,
        records_read=0,
        records_valid=0,
        records_rejected=0,
        warnings=[],
        errors=list(errors),
        processing_time_seconds=0.1,
    )


# --- Punto 1: duplicados -------------------------------------------------------


def test_completed_execution_blocks_same_name_case_insensitive(repository):
    name = _name()
    execution_id = repository.create_execution(name)
    _complete(repository, execution_id)

    found = repository.find_active_execution_by_filename(f"  {name.upper()}  ")
    assert found is not None and found.execution_id == execution_id
    with pytest.raises(DuplicateFileError):
        repository.create_execution(name.upper())


def test_processing_execution_blocks_same_name(repository):
    name = _name()
    repository.create_execution(name)
    with pytest.raises(DuplicateFileError):
        repository.create_execution(name)


def test_failed_execution_does_not_block_name(repository):
    name = _name()
    failed_id = repository.create_execution(name)
    _complete(repository, failed_id, errors=["falló"])

    assert repository.find_active_execution_by_filename(name) is None
    assert repository.create_execution(name) != failed_id


def test_two_simultaneous_uploads_of_same_name_only_one_wins():
    """Dos conexiones insertan el mismo nombre a la vez: la segunda queda
    bloqueada por el índice único parcial hasta que la primera termina (aquí
    se demuestra con lock_timeout, sin confirmar nada)."""
    name = _name()
    insert = text("INSERT INTO etl_execution (filename, status) VALUES (:f, 'processing')")
    with engine.connect() as first, engine.connect() as second:
        first.begin()
        first.execute(insert, {"f": name})

        second.begin()
        second.execute(text("SET LOCAL lock_timeout = '1s'"))
        with pytest.raises(OperationalError, match="lock timeout"):
            second.execute(insert, {"f": name.lower()})
        second.rollback()

        first.rollback()


# --- Punto 2: numeración -------------------------------------------------------


def test_completed_gets_next_number_and_processing_or_failed_get_none(repository, db_session):
    expected = max(
        _counter(),
        db_session.execute(text("SELECT COALESCE(MAX(sesion_label), 0) FROM etl_execution")).scalar(),
    ) + 1

    processing_id = repository.create_execution(_name())
    failed_id = repository.create_execution(_name())
    _complete(repository, failed_id, errors=["falló"])
    completed_id = repository.create_execution(_name())
    _complete(repository, completed_id)

    assert repository.get_execution(processing_id).sesion_label is None
    assert repository.get_execution(failed_id).sesion_label is None
    assert repository.get_execution(completed_id).sesion_label == expected


def _label_in_own_transaction(conn) -> int:
    """Crea una ejecución y la pasa a completed en la transacción de `conn`
    (el trigger asigna el número); devuelve el número asignado."""
    execution_id = conn.execute(
        text("INSERT INTO etl_execution (filename, status) VALUES (:f, 'processing') RETURNING execution_id"),
        {"f": _name()},
    ).scalar()
    return conn.execute(
        text("UPDATE etl_execution SET status = 'completed' WHERE execution_id = :e RETURNING sesion_label"),
        {"e": execution_id},
    ).scalar()


def test_rollback_does_not_consume_number():
    with engine.connect() as conn:
        conn.begin()
        first = _label_in_own_transaction(conn)
        conn.rollback()
    with engine.connect() as conn:
        conn.begin()
        second = _label_in_own_transaction(conn)
        conn.rollback()
    assert first == second


def test_concurrent_completions_never_repeat_number():
    """Mientras una carga sostiene el número (sin confirmar), otra no puede
    tomarlo: queda bloqueada en la fila contador. Cuando la primera hace
    rollback, la segunda obtiene ese mismo número (no hay hueco)."""
    with engine.connect() as first, engine.connect() as second:
        first.begin()
        held = _label_in_own_transaction(first)

        second.begin()
        second.execute(text("SET LOCAL lock_timeout = '1s'"))
        with pytest.raises(OperationalError, match="lock timeout"):
            _label_in_own_transaction(second)
        second.rollback()

        result = {}
        second.begin()
        waiter = threading.Thread(target=lambda: result.update(label=_label_in_own_transaction(second)))
        waiter.start()
        waiter.join(timeout=1)
        assert waiter.is_alive()  # sigue esperando el lock de la primera
        first.rollback()
        waiter.join(timeout=10)
        second.rollback()

    assert result["label"] == held


# --- Por HTTP, de punta a punta (transacción con rollback) -------------------------


def test_http_flow_completed_then_duplicate_upload_and_cancel_are_409(rollback_app, sample_handover_csv_bytes):
    from tests.integration.conftest import unique_csv_name

    client, name = rollback_app.client, unique_csv_name()

    def upload(filename):
        return client.post(
            "/api/v1/ingestion/upload",
            files=[("files", (filename, sample_handover_csv_bytes, "text/csv"))],
            data={"declared_sizes": [str(len(sample_handover_csv_bytes))]},
        )

    first = upload(name)
    assert first.status_code == 200
    upload_data = first.json()[0]["upload"]
    accepted = client.post(
        "/api/v1/ingestion/process",
        json={"stored_filename": upload_data["stored_filename"], "original_filename": name},
    )
    assert accepted.status_code == 202
    assert accepted.json()["sesion_label"] is None  # el número se asigna al completar
    execution_id = accepted.json()["execution_id"]

    status = client.get(f"/api/v1/ingestion/status/{execution_id}").json()
    assert (status["status"], status["etapa"], status["progreso"]) == ("completed", "done", 100)
    assert status["sesion_label"] is not None
    # El temporal se borra al terminar.
    assert not (rollback_app.settings.resolved_data_input_dir() / upload_data["stored_filename"]).exists()

    # Mismo archivo otra vez (otras mayúsculas): 409 y mensaje con la sesión.
    second = upload(name.upper())
    assert second.status_code == 409
    item = second.json()[0]
    assert item["error_code"] == "duplicado"
    assert f"ya fue cargado como Sesión {status['sesion_label']}" in item["error"]

    # Cancelar una ejecución ya confirmada: 409 "ya completada", no deshace nada.
    cancel = client.post(f"/api/v1/ingestion/cancel/{execution_id}")
    assert cancel.status_code == 409
    assert "ya está completada" in cancel.json()["detail"]
    assert client.get(f"/api/v1/ingestion/status/{execution_id}").json()["status"] == "completed"


def test_session_number_comes_from_the_database_never_from_the_filename(rollback_app, sample_handover_csv_bytes):
    """Un archivo "Session_31_..." es la sesión que le asigna la base, nunca
    la 31; y dos archivos con números distintos en el nombre reciben números
    consecutivos según el orden de carga."""
    client = rollback_app.client
    suffix = uuid.uuid4().hex[:8]
    names = [f"Session_31_20240308_{suffix}.csv", f"Session_12_20240309_{suffix}.csv"]

    def load(filename):
        upload_data = client.post(
            "/api/v1/ingestion/upload",
            files=[("files", (filename, sample_handover_csv_bytes, "text/csv"))],
        ).json()[0]["upload"]
        accepted = client.post(
            "/api/v1/ingestion/process",
            json={"stored_filename": upload_data["stored_filename"], "original_filename": filename},
        ).json()
        return client.get(f"/api/v1/ingestion/status/{accepted['execution_id']}").json()

    expected_first = rollback_app.connection.execute(
        text("SELECT GREATEST((SELECT ultimo FROM etl_sesion_contador), (SELECT COALESCE(MAX(sesion_label), 0) FROM etl_execution)) + 1")
    ).scalar()
    first, second = load(names[0]), load(names[1])

    assert (first["status"], second["status"]) == ("completed", "completed")
    assert first["sesion_label"] == expected_first
    assert second["sesion_label"] == expected_first + 1  # consecutivos, en orden de carga
    assert first["sesion_label"] != 31
    assert second["sesion_label"] != 12
    assert first["filename"] == names[0]  # el nombre real se conserva tal cual

    # El rechazo por duplicado y /export hablan de la sesión de la base.
    duplicate = client.post(
        "/api/v1/ingestion/upload",
        files=[("files", (names[0], sample_handover_csv_bytes, "text/csv"))],
    ).json()[0]
    assert f"ya fue cargado como Sesión {first['sesion_label']} " in duplicate["error"]
    assert "Sesión 31" not in duplicate["error"]
    export = client.get(f"/api/v1/ingestion/export?sesion_label={second['sesion_label']}")
    assert export.status_code == 200
    assert f"sesion_{second['sesion_label']}.csv" in export.headers["content-disposition"]
