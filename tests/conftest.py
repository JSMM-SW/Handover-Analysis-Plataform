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
