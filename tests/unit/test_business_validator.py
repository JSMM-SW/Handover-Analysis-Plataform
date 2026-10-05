"""The retired Excel format must not enter the CSV pipeline."""
import pytest
from app.modules.ingesta.etl.extractor import detect_format
from app.modules.ingesta.etl.validator import validate_uploaded_file
from app.shared.config import Settings
from app.shared.exceptions import FileValidationError

@pytest.mark.parametrize("filename", ["session.xlsx", "session.xls", "session.json"])
def test_rejects_non_csv_even_with_legacy_configuration(filename):
    with pytest.raises(FileValidationError):
        validate_uploaded_file(filename, b"content", Settings(allowed_extensions=".xlsx,.xls,.csv"))
    with pytest.raises(FileValidationError):
        detect_format(filename)
