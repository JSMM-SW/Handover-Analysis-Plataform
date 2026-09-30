"""Test de integración end-to-end con el archivo real de tesis.

Sube Datos_Tesis.xlsx a través de los endpoints HTTP reales (/upload y
/process) y verifica el resultado contra Supabase. Requiere DATABASE_URL
configurado en .env. Si el archivo real no está presente en este entorno
(no se versiona: contiene datos de campo del autor), el test se salta.

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
    Path(__file__).resolve().parents[2]
    / "data"
    / "input"
    / "5db4d5d9-6ac0-4044-bda2-c6770c50a4c1_Datos_Tesis.xlsx"
)

pytestmark = pytest.mark.skipif(
    not REAL_FILE_PATH.exists(),
    reason="Datos_Tesis.xlsx no está presente en este entorno (archivo no versionado).",
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


def test_full_pipeline_against_real_file(client, cleanup_execution):
    execution_ids, stored_filenames = cleanup_execution
    content = REAL_FILE_PATH.read_bytes()

    upload_response = client.post(
        "/api/v1/ingestion/upload",
        files=[
            (
                "files",
                (
                    "Datos_Tesis.xlsx",
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            )
        ],
    )
    assert upload_response.status_code == 200
    upload_item = upload_response.json()[0]
    assert upload_item["ok"] is True
    upload_data = upload_item["upload"]
    stored_filenames.append(upload_data["stored_filename"])
    assert len(upload_data["sheets"]) == 3

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
    assert result["records_read"] == 495
    assert result["records_valid"] > 0
    assert result["records_rejected"] > 0
    assert result["records_valid"] + result["records_rejected"] == result["records_read"]
    assert result["sesion_label"] is not None

    status_response = client.get(f"/api/v1/ingestion/status/{result['execution_id']}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["status"] == "completed"
    assert status_data["records_valid"] == result["records_valid"]
    assert status_data["sesion_label"] == result["sesion_label"]

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

    assert valid_count == result["records_valid"]
    assert rejected_count == result["records_rejected"]

    # Punto 1/2: exportación filtrando por execution_id y por sesion_label.
    export_by_execution = client.get(
        f"/api/v1/ingestion/export?execution_id={result['execution_id']}"
    )
    assert export_by_execution.status_code == 200
    assert export_by_execution.headers["content-type"].startswith("text/csv")
    export_rows = export_by_execution.text.strip().splitlines()
    assert len(export_rows) - 1 == result["records_valid"]  # -1 por el encabezado

    export_by_sesion = client.get(
        f"/api/v1/ingestion/export?sesion_label={result['sesion_label']}"
    )
    assert export_by_sesion.status_code == 200
    assert export_by_sesion.text == export_by_execution.text

    # Punto 6: velocidad_kmh presente en el CSV exportado (columna, aunque
    # el valor pueda ser NULL para el primer registro de cada hoja).
    assert "velocidad_kmh" in export_rows[0].split(",")
