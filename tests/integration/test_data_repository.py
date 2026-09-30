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
from sqlalchemy.orm import sessionmaker

from app.shared.config import settings
from app.modules.ingesta.repository import HandoverRepository


@pytest.fixture()
def db_session():
    engine = create_engine(settings.database_url)
    connection = engine.connect()
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
        "rsrp_dbm": -94,
        "archivo_origen": "Datos_Tesis.xlsx",
        "hoja_origen": "Datos 1",
        "origen_formato": "xlsx",
    }


def test_create_execution_returns_uuid(repository):
    execution_id = repository.create_execution(filename="Datos_Tesis.xlsx")
    assert isinstance(execution_id, uuid.UUID)


def test_save_valid_records_inserts_rows(repository, db_session):
    execution_id = repository.create_execution(filename="Datos_Tesis.xlsx")
    records = [_valid_record() for _ in range(3)]

    repository.save_valid_records(execution_id, records)

    count = db_session.execute(
        text("SELECT COUNT(*) FROM handover_record WHERE execution_id = :eid"),
        {"eid": str(execution_id)},
    ).scalar()
    assert count == 3


def test_save_rejected_records_inserts_rows(repository, db_session):
    execution_id = repository.create_execution(filename="Datos_Tesis.xlsx")
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
    execution_id = repository.create_execution(filename="Datos_Tesis.xlsx")

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
    execution_id = repository.create_execution(filename="Datos_Tesis.xlsx")

    repository.finish_execution(
        execution_id,
        records_read=0,
        records_valid=0,
        records_rejected=0,
        warnings=[],
        errors=["Archivo corrupto: no se pudo abrir con openpyxl"],
        processing_time_seconds=0.12,
    )

    status = db_session.execute(
        text("SELECT status FROM etl_execution WHERE execution_id = :eid"),
        {"eid": str(execution_id)},
    ).scalar()
    assert status == "failed"


def test_run_ingestion_persists_filename_verbatim_even_if_uuid_like(
    tmp_path, repository, db_session, sample_handover_xlsx_bytes
):
    """Regresión del incidente de reconciliación: `archivo_origen` en
    handover_record y `filename` en etl_execution deben quedar exactamente
    igual al `original_filename` recibido, incluso si ese nombre ya
    contiene un UUID (el caso adversarial real que causó el incidente).
    Corre dentro de la transacción con rollback de `db_session`: no deja
    datos de prueba en la base compartida.
    """
    from app.shared.config import Settings
    from app.modules.ingesta.schemas import ProcessRequest
    from app.modules.ingesta.services import run_ingestion

    risky_filename = "5db4d5d9-6ac0-4044-bda2-c6770c50a4c1_Datos_Tesis.xlsx"
    stored_filename = "unrelated-stored-name.xlsx"

    settings = Settings(data_input_dir=tmp_path / "input")
    settings.resolved_data_input_dir().joinpath(stored_filename).write_bytes(
        sample_handover_xlsx_bytes
    )

    payload = ProcessRequest(stored_filename=stored_filename, original_filename=risky_filename)
    result = run_ingestion(payload, settings, repository)

    assert result.filename == risky_filename

    persisted_filename = db_session.execute(
        text("SELECT filename FROM etl_execution WHERE execution_id = :eid"),
        {"eid": result.execution_id},
    ).scalar()
    assert persisted_filename == risky_filename

    persisted_archivo_origen = db_session.execute(
        text("SELECT DISTINCT archivo_origen FROM handover_record WHERE execution_id = :eid"),
        {"eid": result.execution_id},
    ).scalars().all()
    assert persisted_archivo_origen == [risky_filename]
