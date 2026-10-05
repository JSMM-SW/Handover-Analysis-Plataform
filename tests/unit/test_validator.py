import pytest

from app.shared.config import Settings
from app.shared.exceptions import FileValidationError
from app.modules.ingesta.etl.validator import validate_uploaded_file


@pytest.fixture
def settings() -> Settings:
    return Settings(max_upload_size_mb=1, allowed_extensions=".csv")


def test_accepts_valid_csv(settings, sample_handover_csv_bytes):
    validate_uploaded_file("handover.csv", sample_handover_csv_bytes, settings)


def test_rejects_wrong_extension(settings, sample_handover_csv_bytes):
    with pytest.raises(FileValidationError, match="no soportada"):
        validate_uploaded_file("handover.xlsx", sample_handover_csv_bytes, settings)


def test_rejects_empty_file(settings):
    with pytest.raises(FileValidationError, match="vacío"):
        validate_uploaded_file("handover.csv", b"", settings)


def test_rejects_oversized_file(settings):
    oversized = b"0" * (settings.max_upload_size_bytes + 1)
    with pytest.raises(FileValidationError, match="tamaño máximo"):
        validate_uploaded_file("handover.csv", oversized, settings)


def test_rejects_missing_filename(settings, sample_handover_csv_bytes):
    with pytest.raises(FileValidationError, match="nombre"):
        validate_uploaded_file("", sample_handover_csv_bytes, settings)
