"""
Tests de integración para HandoverRepository.

Requieren acceso real a la base de datos (Supabase/PostgreSQL) configurada
en `DATABASE_URL` (.env). Cada test corre dentro de una transacción que se
revierte al final (rollback), así que no dejan datos de prueba en la base.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.shared.config import settings
from app.modules.ingesta.repository import HandoverRepository


@pytest.fixture()
def db_session():
    from tests.integration.conftest import test_engine

    connection = test_engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection)
    session = session_factory()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def repository(db_session):
    return HandoverRepository(db_session)


@pytest.fixture()
def background_session_factory(db_session):
    """Sesión para `execute_ingestion` sobre la MISMA conexión de prueba, en
    modo SAVEPOINT: su commit/rollback no toca la transacción externa, que
    igual se revierte al final del test (nada queda en la base compartida)."""
    return lambda: Session(bind=db_session.connection(), join_transaction_mode="create_savepoint")


def _start_and_execute(
    tmp_path, repository, session_factory, content: bytes, filename: str, stored_filename=None
):
    from app.shared.config import Settings
    from app.modules.ingesta.schemas import ProcessRequest
    from app.modules.ingesta.services import execute_ingestion, start_ingestion
    from tests.conftest import NullMonitor

    stored_filename = stored_filename or "stored-" + filename
    settings = Settings(data_input_dir=tmp_path / "input")
    settings.resolved_data_input_dir().joinpath(stored_filename).write_bytes(content)
    payload = ProcessRequest(stored_filename=stored_filename, original_filename=filename)

    result = start_ingestion(payload, settings, repository)
    assert result.status == "processing"
    # El monitor real usa una conexión aparte en autocommit, que no vería la
    # ejecución de prueba (sin confirmar). Avance y cancelación se prueban en
    # tests/integration/test_avance_y_cancelacion.py.
    execute_ingestion(
        uuid.UUID(result.execution_id),
        payload,
        settings,
        session_factory,
        monitor_factory=lambda execution_id, config: NullMonitor(),
    )
    return result


def _valid_record():
    """Un registro típico del dataset real (hoja 'Datos 1')."""
    return {
        "timestamp_medicion": datetime.now(timezone.utc),
        "cell_id": 25949452,
        "tac": 12345,
        "earfcn": 740,
        "tecnologia": 1,
        "latitud": -0.180653,
        "longitud": -78.467838,
        "rssi": -94,
        "archivo_origen": "Session.csv",
        "hoja_origen": "Datos 1",
        "origen_formato": "csv",
    }


def test_create_execution_returns_uuid(repository):
    execution_id = repository.create_execution(filename="Session.csv")
    assert isinstance(execution_id, uuid.UUID)


def test_save_valid_records_inserts_rows(repository, db_session):
    execution_id = repository.create_execution(filename="Session.csv")
    records = [_valid_record() for _ in range(3)]

    repository.save_valid_records(execution_id, records)

    count = db_session.execute(
        text("SELECT COUNT(*) FROM handover_record WHERE execution_id = :eid"),
        {"eid": str(execution_id)},
    ).scalar()
    assert count == 3


def test_save_rejected_records_inserts_rows(repository, db_session):
    execution_id = repository.create_execution(filename="Session.csv")
    rejected = [
        {
            "hoja_origen": "Datos 3",
            "fila_excel": 42,
            "motivo_rechazo": "rsrp = 99 (centinela de error del equipo de medición)",
            "datos_crudos": {"RSRP": 99, "Cell ID/ECI": 0},
        }
    ]

    repository.save_rejected_records(execution_id, rejected)

    count = db_session.execute(
        text("SELECT COUNT(*) FROM handover_record_rejected WHERE execution_id = :eid"),
        {"eid": str(execution_id)},
    ).scalar()
    assert count == 1


def test_finish_execution_updates_status_completed(repository, db_session):
    execution_id = repository.create_execution(filename="Session.csv")

    repository.finish_execution(
        execution_id,
        records_read=495,
        records_valid=472,
        records_rejected=23,
        warnings=["23 registros con RSRP=99 descartados"],
        errors=[],
        processing_time_seconds=1.87,
    )

    status = db_session.execute(
        text("SELECT status FROM etl_execution WHERE execution_id = :eid"),
        {"eid": str(execution_id)},
    ).scalar()
    assert status == "completed"


def test_finish_execution_with_errors_marks_failed(repository, db_session):
    execution_id = repository.create_execution(filename="Session.csv")

    repository.finish_execution(
        execution_id,
        records_read=0,
        records_valid=0,
        records_rejected=0,
        warnings=[],
        errors=["CSV con estructura incompatible"],
        processing_time_seconds=0.12,
    )

    status = db_session.execute(
        text("SELECT status FROM etl_execution WHERE execution_id = :eid"),
        {"eid": str(execution_id)},
    ).scalar()
    assert status == "failed"


def test_ingestion_persists_filename_verbatim_even_if_uuid_like(
    tmp_path, repository, db_session, background_session_factory, sample_handover_csv_bytes
):
    """Regresión del incidente de reconciliación: `archivo_origen` en
    handover_record y `filename` en etl_execution deben quedar exactamente
    igual al `original_filename` recibido, incluso si ese nombre ya
    contiene un UUID (el caso adversarial real que causó el incidente).
    Corre dentro de la transacción con rollback de `db_session`: no deja
    datos de prueba en la base compartida.
    """
    risky_filename = "5db4d5d9-6ac0-4044-bda2-c6770c50a4c1_Session.csv"
    result = _start_and_execute(
        tmp_path,
        repository,
        background_session_factory,
        sample_handover_csv_bytes,
        risky_filename,
        stored_filename="unrelated-stored-name.csv",
    )

    assert result.filename == risky_filename

    status, persisted_filename = db_session.execute(
        text("SELECT status, filename FROM etl_execution WHERE execution_id = :eid"),
        {"eid": result.execution_id},
    ).one()
    assert status == "completed"
    assert persisted_filename == risky_filename

    persisted_archivo_origen = db_session.execute(
        text("SELECT DISTINCT archivo_origen FROM handover_record WHERE execution_id = :eid"),
        {"eid": result.execution_id},
    ).scalars().all()
    assert persisted_archivo_origen == [risky_filename]


def test_copy_load_round_trips_values(
    tmp_path, repository, db_session, background_session_factory, sample_handover_csv_bytes
):
    """El Load por COPY guarda los mismos valores que el pipeline produce
    (tipos, NULLs, texto) y los rechazados con su JSON crudo."""
    result = _start_and_execute(
        tmp_path, repository, background_session_factory, sample_handover_csv_bytes, "sesion.csv"
    )

    rows = db_session.execute(
        text(
            "SELECT tecnologia, tech, net_type, rssi, rsrp, rssnr, latitud "
            "FROM handover_record WHERE execution_id = :eid ORDER BY report_index"
        ),
        {"eid": result.execution_id},
    ).all()
    # rssi se guarda tal cual (sin reparto por tech); rsrp es NULL porque el
    # fixture no trae la columna opcional rssi_strongest.
    # latitud es NUMERIC (Decimal): a float para comparar con approx.
    rows = [(*r[:-1], None if r[-1] is None else float(r[-1])) for r in rows]
    assert [tuple(r) for r in rows] == [
        (1, "LTE", "LTE", -90, None, -9, pytest.approx(-0.180653)),
        (2, "WCDMA", "UMTS", -79, None, None, pytest.approx(-0.1807)),
        (3, "GSM", "GPRS", -107, None, None, None),
    ]

    motivos = db_session.execute(
        text(
            "SELECT motivo_rechazo, datos_crudos->>'cid' FROM handover_record_rejected "
            "WHERE execution_id = :eid ORDER BY fila_excel"
        ),
        {"eid": result.execution_id},
    ).all()
    assert len(motivos) == 2
    assert motivos[0][1] == "2147483647"  # JSONB consultable, no texto plano


def test_unexpected_error_marks_failed_without_orphan_records(
    tmp_path, repository, db_session, background_session_factory, sample_handover_csv_bytes, monkeypatch
):
    """Si algo falla después de insertar (aquí: justo antes del commit), la
    ejecución queda "failed" con el error y sin registros huérfanos, en vez
    de quedar colgada en "processing"."""
    def explode(*args, **kwargs):
        raise RuntimeError("conexión perdida")

    monkeypatch.setattr(HandoverRepository, "save_rejected_records", explode)
    result = _start_and_execute(
        tmp_path, repository, background_session_factory, sample_handover_csv_bytes, "sesion.csv"
    )

    status, errors = db_session.execute(
        text("SELECT status, errors FROM etl_execution WHERE execution_id = :eid"),
        {"eid": result.execution_id},
    ).one()
    assert status == "failed"
    # Mensaje amigable con el identificador; el detalle (tipo, mensaje, traza)
    # va solo al log.
    assert "error inesperado" in errors[0].lower()
    assert result.execution_id in errors[0]
    assert "RuntimeError" not in errors[0]
    orphans = db_session.execute(
        text("SELECT COUNT(*) FROM handover_record WHERE execution_id = :eid"),
        {"eid": result.execution_id},
    ).scalar()
    assert orphans == 0


def test_header_only_file_marks_failed_with_clear_message(
    tmp_path, repository, db_session, background_session_factory
):
    from tests.conftest import CSV_COLUMNS

    content = (";".join(CSV_COLUMNS) + "\n").encode()
    result = _start_and_execute(tmp_path, repository, background_session_factory, content, "vacio.csv")

    status, errors = db_session.execute(
        text("SELECT status, errors FROM etl_execution WHERE execution_id = :eid"),
        {"eid": result.execution_id},
    ).one()
    assert status == "failed"
    assert "no contiene registros" in errors[0]


def test_load_in_batches_is_one_transaction_and_reports_progress(db_session):
    """Varias sentencias COPY (tandas), una sola transacción: todas las filas
    quedan visibles juntas y `on_batch` informa el avance acumulado."""
    repository = HandoverRepository(db_session, load_batch_rows=2)
    execution_id = repository.create_execution(filename="lotes.csv")
    progress = []

    repository.save_valid_records(execution_id, [_valid_record() for _ in range(5)], progress.append)

    assert progress == [2, 4, 5]
    count = db_session.execute(
        text("SELECT COUNT(*) FROM handover_record WHERE execution_id = :eid"),
        {"eid": str(execution_id)},
    ).scalar()
    assert count == 5


def test_connection_lost_during_load_marks_failed_with_clear_message_and_no_rows(
    tmp_path, repository, db_session, background_session_factory, sample_handover_csv_bytes, monkeypatch
):
    """Si la conexión cae a mitad del Load: rollback total, "failed" con un
    mensaje claro (sin detalles internos) y 0 filas de esa ejecución."""
    from sqlalchemy.exc import OperationalError

    from app.modules.ingesta.services import MENSAJE_CONEXION_PERDIDA

    def drop_connection(*args, **kwargs):
        raise OperationalError("COPY", {}, Exception("server closed the connection unexpectedly"))

    monkeypatch.setattr(HandoverRepository, "save_rejected_records", drop_connection)
    result = _start_and_execute(
        tmp_path, repository, background_session_factory, sample_handover_csv_bytes, "sesion.csv"
    )

    status, errors, sesion_label = db_session.execute(
        text("SELECT status, errors, sesion_label FROM etl_execution WHERE execution_id = :eid"),
        {"eid": result.execution_id},
    ).one()
    assert status == "failed"
    assert errors == [MENSAJE_CONEXION_PERDIDA]
    assert sesion_label is None  # un fallo no consume número de sesión
    for table in ("handover_record", "handover_record_rejected"):
        rows = db_session.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE execution_id = :eid"), {"eid": result.execution_id}
        ).scalar()
        assert rows == 0
