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
