"""Test de integración end-to-end con el export real de NetMonitor Lite
(Session_43_20260623_165825.csv, 86,398 filas, 45 columnas).

Sube el archivo a través de los endpoints HTTP reales (/upload y /process) y
verifica el resultado contra Supabase. Requiere DATABASE_URL configurado en
.env. Si el archivo real no está presente en este entorno (no se versiona:
datos de campo de Marcelo/Módulo 2), el test se salta.
Corre dentro de una única transacción que se revierte al final (fixture
`rollback_app`): pasa por los endpoints HTTP reales, pero no confirma nada en
la base compartida, ningún otro módulo ve la sesión de prueba y no se consume
número de sesión. El archivo se sube con un nombre de prueba único, porque el
nombre real puede estar ya cargado y la carga lo rechazaría como duplicado.
"""

from pathlib import Path

import pytest
from sqlalchemy import text

from tests.integration.conftest import unique_csv_name

REAL_FILE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "input" / "Session_43_20260623_165825.csv"
)

pytestmark = pytest.mark.skipif(
    not REAL_FILE_PATH.exists(),
    reason="Session_43_20260623_165825.csv no está presente en este entorno (archivo no versionado).",
)


def test_full_pipeline_against_real_session43(rollback_app):
    client, conn = rollback_app.client, rollback_app.connection
    content = REAL_FILE_PATH.read_bytes()
    filename = unique_csv_name()

    upload_response = client.post(
        "/api/v1/ingestion/upload",
        files=[("files", (filename, content, "text/csv"))],
    )
    assert upload_response.status_code == 200
    upload_item = upload_response.json()[0]
    assert upload_item["ok"] is True
    upload_data = upload_item["upload"]
    assert upload_data["sheets"][0]["num_rows"] == 86398

    process_response = client.post(
        "/api/v1/ingestion/process",
        json={
            "stored_filename": upload_data["stored_filename"],
            "original_filename": upload_data["original_filename"],
        },
    )
    assert process_response.status_code == 202
    accepted = process_response.json()
    assert accepted["status"] == "processing"
    # /process responde de inmediato y procesa en segundo plano. TestClient
    # ejecuta las BackgroundTasks antes de devolver la respuesta, así que el
    # resultado final ya está disponible en /status.
    result = client.get(f"/api/v1/ingestion/status/{accepted['execution_id']}").json()

    assert result["status"] == "completed"
    assert result["records_read"] == 86398
    assert result["records_valid"] > 0
    assert result["records_rejected"] > 0
    assert result["records_valid"] + result["records_rejected"] == result["records_read"]

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
