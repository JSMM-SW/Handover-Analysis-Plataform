"""Test de integración end-to-end con el archivo real de tesis.

Sube Datos_Tesis.xlsx a través de los endpoints HTTP reales (/upload y
/process) y verifica el resultado contra Supabase. Requiere DATABASE_URL
configurado en .env. Si el archivo real no está presente en este entorno
(no se versiona: contiene datos de campo del autor), el test se salta.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import settings
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


def test_full_pipeline_against_real_file(client):
    content = REAL_FILE_PATH.read_bytes()

    upload_response = client.post(
        "/api/v1/ingestion/upload",
        files={
            "file": (
                "Datos_Tesis.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_response.status_code == 200
    upload_data = upload_response.json()
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

    assert result["status"] == "completed"
    assert result["records_read"] == 495
    assert result["records_valid"] > 0
    assert result["records_rejected"] > 0
    assert result["records_valid"] + result["records_rejected"] == result["records_read"]

    status_response = client.get(f"/api/v1/ingestion/status/{result['execution_id']}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["status"] == "completed"
    assert status_data["records_valid"] == result["records_valid"]

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
