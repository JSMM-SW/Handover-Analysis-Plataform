"""Test de integración end-to-end con un CSV real de Network Cell Info.

Sube Session_5_20260505_084058.csv (2,824 filas, delimitador ';') a través
de los endpoints HTTP reales (/upload y /process) y verifica el resultado
contra Supabase. Requiere DATABASE_URL configurado en .env. Si el archivo
real no está presente en este entorno (no se versiona: datos de campo del
autor), el test se salta.

Este test pasa por endpoints HTTP reales (cada request abre y confirma su
propia sesión de base de datos), así que no puede envolverse en una única
transacción con rollback como los tests de HandoverRepository. En su lugar,
borra explícitamente la fila de `etl_execution` que crea (con cascada a
handover_record/handover_record_rejected) al final, para no dejar datos de
prueba en la base compartida de Supabase.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.shared.config import settings
from app.main import app

REAL_FILE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "input" / "Session_5_20260505_084058.csv"
)

pytestmark = pytest.mark.skipif(
    not REAL_FILE_PATH.exists(),
    reason="Session_5_20260505_084058.csv no está presente en este entorno (archivo no versionado).",
)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def cleanup_execution():
    execution_ids: list[str] = []
    stored_filenames: list[str] = []
    yield execution_ids, stored_filenames

    for stored_filename in stored_filenames:
        path = settings.resolved_data_input_dir() / stored_filename
        path.unlink(missing_ok=True)

    if not execution_ids:
        return
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM etl_execution WHERE execution_id = ANY(:ids)"),
            {"ids": execution_ids},
        )


def test_full_pipeline_against_real_csv(client, cleanup_execution):
    execution_ids, stored_filenames = cleanup_execution
    content = REAL_FILE_PATH.read_bytes()

    upload_response = client.post(
        "/api/v1/ingestion/upload",
        files=[("files", ("Session_5_20260505_084058.csv", content, "text/csv"))],
    )
    assert upload_response.status_code == 200
    upload_item = upload_response.json()[0]
    assert upload_item["ok"] is True
    upload_data = upload_item["upload"]
    stored_filenames.append(upload_data["stored_filename"])
    assert upload_data["sheets"][0]["num_rows"] == 2824  # sin contar encabezado

    process_response = client.post(
        "/api/v1/ingestion/process",
        json={
            "stored_filename": upload_data["stored_filename"],
            "original_filename": upload_data["original_filename"],
        },
    )
    assert process_response.status_code == 200
    result = process_response.json()
    execution_ids.append(result["execution_id"])

    assert result["status"] == "completed"
    assert result["records_read"] == 2824
    assert result["records_valid"] > 0
    assert result["records_rejected"] > 0
    assert result["records_valid"] + result["records_rejected"] == result["records_read"]

    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        valid_count = conn.execute(
            text("SELECT COUNT(*) FROM handover_record WHERE execution_id = :eid"),
            {"eid": result["execution_id"]},
        ).scalar()
        rejected_count = conn.execute(
            text("SELECT COUNT(*) FROM handover_record_rejected WHERE execution_id = :eid"),
            {"eid": result["execution_id"]},
        ).scalar()
        origen_formato = conn.execute(
            text(
                "SELECT DISTINCT origen_formato FROM handover_record WHERE execution_id = :eid"
            ),
            {"eid": result["execution_id"]},
        ).scalars().all()
        motivos = conn.execute(
            text(
                "SELECT motivo_rechazo, COUNT(*) FROM handover_record_rejected "
                "WHERE execution_id = :eid GROUP BY motivo_rechazo"
            ),
            {"eid": result["execution_id"]},
        ).all()

    assert valid_count == result["records_valid"]
    assert rejected_count == result["records_rejected"]
    assert origen_formato == ["csv"]
    assert len(motivos) > 0
    assert result["sesion_label"] is not None

    # Punto 6: al menos un registro con velocidad_kmh calculada (no el
    # primero de la sesión). Session_5 es una sola sesión continua (no tiene
    # hojas), así que casi todos los registros tienen un anterior real.
    with engine.connect() as conn:
        with_velocity = conn.execute(
            text(
                "SELECT COUNT(*) FROM handover_record "
                "WHERE execution_id = :eid AND velocidad_kmh IS NOT NULL"
            ),
            {"eid": result["execution_id"]},
        ).scalar()
    assert with_velocity > 0

    export_response = client.get(f"/api/v1/ingestion/export?sesion_label={result['sesion_label']}")
    assert export_response.status_code == 200
    export_rows = export_response.text.strip().splitlines()
    assert len(export_rows) - 1 == result["records_valid"]
