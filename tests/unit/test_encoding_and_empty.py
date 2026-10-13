"""Codificaciones típicas de exportar desde Windows/Excel (UTF-8 con BOM,
Latin-1/cp1252) y archivos sin registros de datos."""

import pytest

from app.shared.config import Settings
from app.shared.exceptions import ExtractionError, FileValidationError
from app.modules.ingesta.etl.extractor import MENSAJE_SIN_REGISTROS, detect_csv_encoding
from app.modules.ingesta.services import handle_upload, run_pipeline
from tests.conftest import CSV_COLUMNS

HEADER = ";".join(CSV_COLUMNS)
# data_state con tilde: el texto debe llegar intacto al registro final.
ROW = "20260505084058;-0.18;-78.46;3;28886;192;61;-90;-15;-9;1;33171;740;LTE;0;LTE;DESCONEXIÓN;IDLE"


def _csv(tmp_path, text: str, encoding: str, bom: bool = False):
    path = tmp_path / "sesion.csv"
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode(encoding))
    return path


@pytest.mark.parametrize(
    "encoding, bom, detected",
    [("utf-8", True, "utf-8-sig"), ("utf-8", False, "utf-8-sig"), ("latin-1", False, "cp1252")],
)
def test_csv_encodings_parse_and_keep_text_intact(tmp_path, encoding, bom, detected):
    # Columna extra con tilde en el encabezado y en el valor: no debe romper nada.
    path = _csv(tmp_path, f"{HEADER};Operador Teléfono\n{ROW};Telefónica\n", encoding, bom)

    assert detect_csv_encoding(path) == detected
    result = run_pipeline(path, "sesion.csv", "t")

    [record] = result.valid_records
    assert record["cell_id"] == 192
    assert record["timestamp_medicion"].year == 2026  # sys_time (1a columna) leída pese al BOM
    assert record["data_state"] == "DESCONEXIÓN"


def test_bom_does_not_hide_first_column(tmp_path):
    """Con BOM, antes la primera columna se leía como '\\ufeffsys_time' y el
    archivo se rechazaba por "falta sys_time"."""
    path = _csv(tmp_path, f"{HEADER}\n{ROW}\n", "utf-8", bom=True)
    assert len(run_pipeline(path, "sesion.csv", "t").valid_records) == 1


@pytest.mark.parametrize("text", [f"{HEADER}\n", f"{HEADER}\n\n\n", f"{HEADER}\r\n"])
def test_csv_header_only_is_rejected_with_clear_message(tmp_path, text):
    path = _csv(tmp_path, text, "utf-8")
    with pytest.raises(ExtractionError, match="no contiene registros"):
        run_pipeline(path, "sesion.csv", "t")


@pytest.fixture
def upload_settings(tmp_path):
    return Settings(data_input_dir=str(tmp_path))


def test_upload_rejects_header_only_csv(upload_settings):
    with pytest.raises(ExtractionError) as exc:
        handle_upload("sesion.csv", f"{HEADER}\n".encode(), upload_settings)
    assert str(exc.value) == MENSAJE_SIN_REGISTROS


def test_upload_rejects_zero_byte_file(upload_settings):
    with pytest.raises(FileValidationError, match="vacío"):
        handle_upload("sesion.csv", b"", upload_settings)


def test_upload_accepts_latin1_csv(upload_settings):
    content = f"{HEADER}\n{ROW}\n".encode("latin-1")
    response = handle_upload("sesion.csv", content, upload_settings)
    assert response.sheets[0].num_rows == 1
