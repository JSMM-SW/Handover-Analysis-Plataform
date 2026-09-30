import io

import openpyxl
import pytest


def make_xlsx_bytes(sheets: dict[str, list[list]]) -> bytes:
    """Construye un .xlsx en memoria a partir de {nombre_hoja: filas}."""
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)

    for sheet_name, rows in sheets.items():
        worksheet = workbook.create_sheet(title=sheet_name)
        for row in rows:
            worksheet.append(row)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def sample_xlsx_bytes() -> bytes:
    return make_xlsx_bytes(
        {
            "Handover": [
                ["timestamp", "rsrp", "rsrq", "cell_id"],
                ["2026-01-01 10:00:00", -95, -10, "CELL01"],
                ["2026-01-01 10:00:05", -97, -11, "CELL02"],
            ]
        }
    )


HANDOVER_COLUMNS = [
    "Fecha",
    "Hora",
    "Cell ID/ECI",
    "TAC/LAC",
    "PCI/PSC",
    "EARFCN",
    "Tecnología",
    "Latitud",
    "Longitud",
    "Column10",
    "RSRP",
    "Column12",
    "Dirección - distancia GPS",
]


@pytest.fixture
def sample_handover_xlsx_bytes() -> bytes:
    """Estructura real del Excel de handover (13 columnas, incluidas las que
    se descartan), con una mezcla de filas válidas e inválidas conocidas:
    una fila válida, una con cell_id=0 (sentinela), una con gps sin fix y
    una duplicada exacta de la primera.
    """
    valid_row = [
        20260506, 184915, 25949452, 50240, "-", 740, 1, -0.290748, -78.550426, "-", -94, "-", "-",
    ]
    sentinel_row = [
        20260506, 184914, 0, 0, "-", 0, 0, -0.290748, -78.550426, "-", 99, "-", "-",
    ]
    gps_sin_fix_row = [
        20260506, 185741, 26044427, 50240, "-", 740, 1, 0.0, 0.0, "-", -89, "-", "-",
    ]
    return make_xlsx_bytes(
        {
            "Datos 1": [
                HANDOVER_COLUMNS,
                valid_row,
                sentinel_row,
                gps_sin_fix_row,
                valid_row,  # duplicado exacto de la primera fila
            ]
        }
    )


CSV_COLUMNS = [
    "sys_time",
    "lat",
    "long",
    "accuracy",
    "node_id",
    "cid",
    "psc_pci",
    "rssi",
    "rsrq",
    "rssnr",
    "gps",
    "lac_tac",
    "arfcn",
    "net_type",
]


@pytest.fixture
def sample_handover_csv_bytes() -> bytes:
    """CSV con delimitador ';' (como los archivos de sesión individual reales),
    con una mezcla de filas conocidas: una válida LTE, una válida UMTS con
    rssnr centinela (se guarda con warning, no se rechaza), una con cid
    centinela (se rechaza), una con gps sin fix (se rechaza), y un duplicado
    exacto de la primera.
    """
    SENTINEL = 2147483647
    valid_lte_row = [
        20260505084058, -0.180653, -78.467838, 3, 28886, 192, 61, -90, -15, -9, 1, 33171, 740, "LTE",
    ]
    valid_umts_with_rssnr_sentinel_row = [
        20260505084100, -0.180700, -78.467900, 5, 11, 29296, 476, -79, -12, SENTINEL, 1, 33171, 850, "UMTS",
    ]
    cid_sentinel_row = [
        20260505084101, -0.180750, -78.467950, 3, SENTINEL, SENTINEL, 476, -100, -12, SENTINEL, 1, 65535, 850, "LTE",
    ]
    gps_sin_fix_row = [
        20260505084102, -1, -1, -1, 28886, 209, 61, -107, -13, SENTINEL, 0, 33171, 740, "LTE",
    ]
    rows = [
        CSV_COLUMNS,
        valid_lte_row,
        valid_umts_with_rssnr_sentinel_row,
        cid_sentinel_row,
        gps_sin_fix_row,
        valid_lte_row,  # duplicado exacto de la primera fila
    ]
    lines = [";".join(str(v) for v in row) for row in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")
