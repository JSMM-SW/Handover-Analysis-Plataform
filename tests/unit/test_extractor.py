import pytest

from app.shared.exceptions import ExtractionError
from app.modules.ingesta.etl.extractor import extract_basic_info


def test_extracts_sheet_info(tmp_path, sample_xlsx_bytes):
    path = tmp_path / "handover.xlsx"
    path.write_bytes(sample_xlsx_bytes)

    sheets = extract_basic_info(path, execution_id="test-exec")

    assert len(sheets) == 1
    sheet = sheets[0]
    assert sheet.name == "Handover"
    assert sheet.num_rows == 3
    assert sheet.num_cols == 4
    assert sheet.headers == ["timestamp", "rsrp", "rsrq", "cell_id"]


def test_rejects_corrupt_file(tmp_path):
    path = tmp_path / "corrupto.xlsx"
    path.write_bytes(b"esto no es un archivo excel")

    with pytest.raises(ExtractionError):
        extract_basic_info(path, execution_id="test-exec")
