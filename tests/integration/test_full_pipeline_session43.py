"""Test de integración end-to-end con el export real de NetMonitor Lite
(Session_43_20260623_165825.csv, 86,398 filas, 45 columnas).

Sube el archivo a través de los endpoints HTTP reales (/upload y /process) y
verifica el resultado contra Supabase. Requiere DATABASE_URL configurado en
.env. Si el archivo real no está presente en este entorno (no se versiona:
datos de campo de Marcelo/Módulo 2), el test se salta.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.shared.config import settings
from app.main import app

REAL_FILE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "input" / "Session_43_20260623_165825.csv"
)

pytestmark = pytest.mark.skipif(
    not REAL_FILE_PATH.exists(),
    reason="Session_43_20260623_165825.csv no está presente en este entorno (archivo no versionado).",
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


def test_full_pipeline_against_real_session43(client, cleanup_execution):
    execution_ids, stored_filenames = cleanup_execution
    content = REAL_FILE_PATH.read_bytes()

    upload_response = client.post(
        "/api/v1/ingestion/upload",
        files=[("files", ("Session_43_20260623_165825.csv", content, "text/csv"))],
    )
    assert upload_response.status_code == 200
    upload_item = upload_response.json()[0]
    assert upload_item["ok"] is True
    upload_data = upload_item["upload"]
    stored_filenames.append(upload_data["stored_filename"])
    assert upload_data["sheets"][0]["num_rows"] == 86398

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
    assert result["records_read"] == 86398
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
        motivos = conn.execute(
            text(
                "SELECT motivo_rechazo, COUNT(*) FROM handover_record_rejected "
                "WHERE execution_id = :eid GROUP BY motivo_rechazo ORDER BY 2 DESC"
            ),
            {"eid": result["execution_id"]},
        ).all()
        tecnologia_dist = conn.execute(
            text(
                "SELECT tecnologia, COUNT(*) FROM handover_record "
                "WHERE execution_id = :eid GROUP BY tecnologia ORDER BY 1"
            ),
            {"eid": result["execution_id"]},
        ).all()
        sample = conn.execute(
            text(
                "SELECT tech, net_type, tecnologia, rssi, rsrq, rsrp, "
                "cid, node_id, lac_tac_raw, report_index "
                "FROM handover_record WHERE execution_id = :eid "
                "ORDER BY report_index LIMIT 5"
            ),
            {"eid": result["execution_id"]},
        ).all()

    assert valid_count == result["records_valid"]
    assert rejected_count == result["records_rejected"]

    print("\n=== RESUMEN Session_43_20260623_165825.csv ===")
    print(f"leídos={result['records_read']} validos={result['records_valid']} rechazados={result['records_rejected']}")
    print("rechazos por motivo:", motivos)
    print("tecnologia (0=sin señal,1=LTE,2=3G,3=2G):", tecnologia_dist)
    print("muestra de 5 filas (tech, net_type, tecnologia, rssi, rsrq, rsrp, cid, node_id, lac_tac_raw, report_index):")
    for row in sample:
        print(" ", row)
