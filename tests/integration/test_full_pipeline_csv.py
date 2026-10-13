"""Test de integración end-to-end con un CSV real de Network Cell Info.

Sube Session_5_20260505_084058.csv (2,824 filas, delimitador ';') a través
de los endpoints HTTP reales (/upload y /process) y verifica el resultado
contra Supabase. Requiere DATABASE_URL configurado en .env. Si el archivo
real no está presente en este entorno (no se versiona: datos de campo del
autor), el test se salta.
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
    Path(__file__).resolve().parents[2] / "data" / "input" / "Session_5_20260505_084058.csv"
)

pytestmark = pytest.mark.skipif(
    not REAL_FILE_PATH.exists(),
    reason="Session_5_20260505_084058.csv no está presente en este entorno (archivo no versionado).",
)


def test_full_pipeline_against_real_csv(rollback_app):
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
    assert upload_data["sheets"][0]["num_rows"] == 2824  # sin contar encabezado

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
    assert result["records_read"] == 2824
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
