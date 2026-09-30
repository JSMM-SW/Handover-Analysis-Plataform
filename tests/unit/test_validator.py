import pytest

from app.shared.config import Settings
from app.shared.exceptions import FileValidationError
from app.modules.ingesta.etl.validator import validate_uploaded_file


@pytest.fixture
def settings() -> Settings:
    return Settings(max_upload_size_mb=1, allowed_extensions=".xlsx")


def test_accepts_valid_xlsx(settings, sample_xlsx_bytes):
    validate_uploaded_file("handover.xlsx", sample_xlsx_bytes, settings)


def test_rejects_wrong_extension(settings, sample_xlsx_bytes):
    with pytest.raises(FileValidationError, match="no soportada"):
        validate_uploaded_file("handover.csv", sample_xlsx_bytes, settings)


def test_rejects_empty_file(settings):
    with pytest.raises(FileValidationError, match="vacío"):
        validate_uploaded_file("handover.xlsx", b"", settings)


def test_rejects_oversized_file(settings):
    oversized = b"0" * (settings.max_upload_size_bytes + 1)
    with pytest.raises(FileValidationError, match="tamaño máximo"):
        validate_uploaded_file("handover.xlsx", oversized, settings)


def test_rejects_missing_filename(settings, sample_xlsx_bytes):
    with pytest.raises(FileValidationError, match="nombre"):
        validate_uploaded_file("", sample_xlsx_bytes, settings)
