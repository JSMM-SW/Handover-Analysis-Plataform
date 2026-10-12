"""Tolerancia del ETL a variaciones razonables de estructura: solo timestamp
y celda son obligatorios; cualquier otra columna esperada puede faltar
(NULL + un warning por ejecución), los encabezados se buscan por nombre sin
importar orden, mayúsculas, tildes, espacios o '_' vs ' ', y un valor no
interpretable rechaza su fila, nunca el archivo.
"""

import pytest

from app.shared.exceptions import SchemaValidationError
from app.modules.ingesta.etl.constants import (
    MOTIVO_CELDA_AUSENTE,
    MOTIVO_TECNOLOGIA_AUSENTE,
    MOTIVO_VALOR_NO_INTERPRETABLE,
)
from app.modules.ingesta.etl.extractor import normalize_header, resolve_columns
from app.modules.ingesta.services import run_pipeline
from tests.conftest import CSV_COLUMNS

LTE_ROW = {
    "sys_time": 20260505084058, "lat": -0.180653, "long": -78.467838, "accuracy": 3,
    "node_id": 28886, "cid": 192, "psc_pci": 61, "rssi": -90, "rsrq": -15, "rssnr": -9,
    "gps": 1, "lac_tac": 33171, "arfcn": 740, "net_type": "LTE", "report": 0, "tech": "LTE",
    "data_state": "CONNECTED", "call_state": "IDLE",
}


def _write_csv(tmp_path, headers: list[str], rows: list[dict], name="sesion.csv"):
    """`headers` son los encabezados tal cual se escriben; cada fila se toma
    de `rows` por el nombre canónico (normalizado) de cada encabezado."""
    lines = [";".join(headers)]
    for row in rows:
        by_norm = {normalize_header(k): v for k, v in row.items()}
        lines.append(";".join("" if by_norm.get(normalize_header(h)) is None
                              else str(by_norm[normalize_header(h)]) for h in headers))
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _row(**overrides) -> dict:
    return {**LTE_ROW, **overrides}


@pytest.mark.parametrize("header", ["Cell ID", "cell_id", " Cell  Id ", "CELL_ID", "﻿Cell ID"])
def test_normalize_header_equivalences(header):
    assert normalize_header(header) == "cell_id"


def test_normalize_header_ignores_accents():
    assert normalize_header("Tecnologia") == normalize_header("Tecnología")


def test_resolve_columns_uses_aliases_and_first_match():
    resolved = resolve_columns(
        ["cell_id", "Cell ID", "fecha"], ["Cell ID/ECI", "Fecha", "RSRP"], {"Cell ID/ECI": ["Cell ID"]}
    )
    assert resolved == {"Cell ID/ECI": "cell_id", "Fecha": "fecha"}


def test_csv_headers_in_other_order_and_case_give_same_result(tmp_path):
    base = run_pipeline(_write_csv(tmp_path, CSV_COLUMNS, [_row()], "a.csv"), "a.csv", "t")
    shuffled = [f"  {h.upper()} " for h in reversed(CSV_COLUMNS)]
    other = run_pipeline(_write_csv(tmp_path, shuffled, [_row()], "b.csv"), "b.csv", "t")

    strip = lambda r: {k: v for k, v in r.items() if k != "archivo_origen"}  # noqa: E731
    assert [strip(r) for r in other.valid_records] == [strip(r) for r in base.valid_records]
    assert other.warnings == base.warnings


def test_csv_extra_columns_are_ignored(tmp_path):
    headers = ["band", *CSV_COLUMNS, "site_name", ""]
    result = run_pipeline(_write_csv(tmp_path, headers, [_row()]), "sesion.csv", "t")
    assert len(result.valid_records) == 1
    assert not any("ausente" in w for w in result.warnings)


def test_csv_missing_optional_columns_are_null_with_one_warning_each(tmp_path):
    missing = ["rsrq", "rssnr", "psc_pci", "accuracy", "report", "data_state"]
    headers = [h for h in CSV_COLUMNS if h not in missing]
    rows = [_row(sys_time=20260505084050 + i, cid=192 + i) for i in range(3)]

    result = run_pipeline(_write_csv(tmp_path, headers, rows), "sesion.csv", "t")

    assert (result.records_read, len(result.valid_records), len(result.rejected_records)) == (3, 3, 0)
    for record in result.valid_records:
        for field in ("rsrq", "rssnr", "psc_pci", "accuracy", "report_index", "data_state"):
            assert record[field] is None
        assert record["rssi"] == -90  # lo que sí vino se conserva
    for column in missing:
        assert sum(f"Columna '{column}' ausente" in w for w in result.warnings) == 1


def test_csv_missing_net_type_keeps_rows_with_null_net_type(tmp_path):
    headers = [h for h in CSV_COLUMNS if h != "net_type"]
    result = run_pipeline(_write_csv(tmp_path, headers, [_row()]), "sesion.csv", "t")

    [record] = result.valid_records
    assert record["net_type"] is None
    assert record["tecnologia"] == 1  # sale de tech
    assert any("Columna 'net_type' ausente" in w for w in result.warnings)


def test_csv_missing_tech_rejects_rows_not_file(tmp_path):
    headers = [h for h in CSV_COLUMNS if h != "tech"]
    result = run_pipeline(_write_csv(tmp_path, headers, [_row()]), "sesion.csv", "t")

    assert result.valid_records == []
    assert [r["motivo_rechazo"] for r in result.rejected_records] == [MOTIVO_TECNOLOGIA_AUSENTE]
    assert any("Columna 'tech' ausente" in w for w in result.warnings)


def test_csv_net_type_vs_tech_audit_warning_is_aggregated(tmp_path):
    rows = [
        _row(),
        _row(sys_time=20260505084059, cid=193, net_type="HSPA"),
        _row(sys_time=20260505084100, cid=194, net_type="UNKNOWN"),
    ]
    result = run_pipeline(_write_csv(tmp_path, CSV_COLUMNS, rows), "sesion.csv", "t")

    assert [r["tecnologia"] for r in result.valid_records] == [1, 1, 1]
    assert any(w.startswith("1 registro(s) csv donde net_type sugiere") for w in result.warnings)
    assert any(w.startswith("1 registro(s) csv con net_type no reconocido") for w in result.warnings)


def test_csv_missing_lat_or_long_nulls_both(tmp_path):
    headers = [h for h in CSV_COLUMNS if h != "long"]
    result = run_pipeline(_write_csv(tmp_path, headers, [_row()]), "sesion.csv", "t")
    [record] = result.valid_records
    assert record["latitud"] is None and record["longitud"] is None


@pytest.mark.parametrize("mandatory", ["sys_time", "cid"])
def test_csv_missing_mandatory_column_rejects_file(tmp_path, mandatory):
    headers = [h for h in CSV_COLUMNS if h != mandatory]
    with pytest.raises(SchemaValidationError, match=mandatory):
        run_pipeline(_write_csv(tmp_path, headers, [_row()]), "sesion.csv", "t")


def test_csv_empty_cells_become_null_and_empty_cid_rejects_only_that_row(tmp_path):
    rows = [
        _row(rsrq=None, arfcn=None, node_id=None),
        _row(sys_time=20260505084059, cid=None),
    ]
    result = run_pipeline(_write_csv(tmp_path, CSV_COLUMNS, rows), "sesion.csv", "t")

    [record] = result.valid_records
    assert record["rsrq"] is None and record["earfcn"] is None and record["node_id"] is None
    assert [r["motivo_rechazo"] for r in result.rejected_records] == [MOTIVO_CELDA_AUSENTE]


def test_csv_unparseable_value_rejects_row_not_file(tmp_path):
    rows = [_row(), _row(sys_time=20260505084059, cid=193, rsrq="abc")]
    result = run_pipeline(_write_csv(tmp_path, CSV_COLUMNS, rows), "sesion.csv", "t")

    assert len(result.valid_records) == 1
    [rejected] = result.rejected_records
    assert rejected["motivo_rechazo"].startswith(MOTIVO_VALOR_NO_INTERPRETABLE)
