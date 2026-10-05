import pytest
from app.shared.exceptions import ExtractionError
from app.modules.ingesta.etl.extractor import extract_csv_preview, extract_records_csv

def test_extracts_csv_info(tmp_path, sample_handover_csv_bytes):
    path = tmp_path / "session.csv"
    path.write_bytes(sample_handover_csv_bytes)
    info = extract_csv_preview(path, "test")[0]
    assert info.num_rows == 5
    assert "rssi" in info.headers
    assert len(extract_records_csv(path, "test")) == 5

def test_rejects_empty_file(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_bytes(b"")
    with pytest.raises(ExtractionError):
        extract_csv_preview(path, "test")

def test_preserves_optional_strongest_and_utf8_bom(tmp_path, sample_handover_csv_bytes):
    lines = sample_handover_csv_bytes.decode("utf-8").splitlines()
    lines = [lines[0] + ";rssi_strongest"] + [line + ";-77" for line in lines[1:]]
    path = tmp_path / "session.csv"
    path.write_text("\n".join(lines), encoding="utf-8-sig")
    assert "rssi_strongest" in extract_csv_preview(path, "test")[0].headers
    assert extract_records_csv(path, "test")[0]["data"]["rssi_strongest"] == -77
