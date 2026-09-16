from app.shared.exceptions import SchemaValidationError
from app.modules.ingesta.etl.constants import (
    MOTIVO_CELL_ID_CERO,
    MOTIVO_CID_CENTINELA,
    MOTIVO_DUPLICADO,
    MOTIVO_GPS_SIN_FIX,
    MOTIVO_GPS_SIN_FIX_CSV,
)
from app.modules.ingesta.services import run_pipeline


def test_pipeline_end_to_end_with_known_bad_rows(tmp_path, sample_handover_xlsx_bytes):
    path = tmp_path / "handover.xlsx"
    path.write_bytes(sample_handover_xlsx_bytes)

    result = run_pipeline(path, archivo_origen="handover.xlsx", execution_id="test-exec")

    # La fixture tiene 4 filas: válida, sentinela (cell_id=0), gps sin fix,
    # y un duplicado exacto de la válida.
    assert result.records_read == 4
    assert len(result.valid_records) == 1
    assert len(result.rejected_records) == 3

    motivos = {r["motivo_rechazo"] for r in result.rejected_records}
    assert motivos == {MOTIVO_CELL_ID_CERO, MOTIVO_GPS_SIN_FIX, MOTIVO_DUPLICADO}

    valid = result.valid_records[0]
    assert valid["cell_id"] == 25949452
    assert valid["hoja_origen"] == "Datos 1"
    assert valid["archivo_origen"] == "handover.xlsx"


def test_pipeline_rejects_file_with_missing_columns(tmp_path, sample_xlsx_bytes):
    path = tmp_path / "generico.xlsx"
    path.write_bytes(sample_xlsx_bytes)

    try:
        run_pipeline(path, archivo_origen="generico.xlsx", execution_id="test-exec")
        assert False, "se esperaba SchemaValidationError"
    except SchemaValidationError as exc:
        assert "estructura esperada" in str(exc)


def test_pipeline_csv_end_to_end_with_known_rows(tmp_path, sample_handover_csv_bytes):
    path = tmp_path / "handover.csv"
    path.write_bytes(sample_handover_csv_bytes)

    result = run_pipeline(path, archivo_origen="handover.csv", execution_id="test-exec")

    # 5 filas: válida LTE, válida UMTS con rssnr centinela, cid centinela
    # (rechazada), gps sin fix (rechazada), duplicado exacto de la primera.
    assert result.records_read == 5
    assert len(result.valid_records) == 2
    assert len(result.rejected_records) == 3

    motivos = {r["motivo_rechazo"] for r in result.rejected_records}
    assert motivos == {MOTIVO_CID_CENTINELA, MOTIVO_GPS_SIN_FIX_CSV, MOTIVO_DUPLICADO}

    valid_by_tecnologia = {r["tecnologia"]: r for r in result.valid_records}
    assert valid_by_tecnologia[1]["cell_id"] == 192  # LTE
    assert valid_by_tecnologia[1]["rsrp_dbm"] is None
    assert valid_by_tecnologia[1]["origen_formato"] == "csv"
    assert valid_by_tecnologia[1]["hoja_origen"] is None

    assert valid_by_tecnologia[2]["cell_id"] == 29296  # UMTS
    assert valid_by_tecnologia[2]["rssnr"] is None  # centinela nuleado

    assert any("rssnr" in w for w in result.warnings)
