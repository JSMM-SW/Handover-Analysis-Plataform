class IngestionError(Exception):
    """Base class for errors raised during file ingestion."""


class FileValidationError(IngestionError):
    """Raised when an uploaded file fails file-level validation
    (extension, size or empty content) before any parsing is attempted.
    """


class ExtractionError(IngestionError):
    """Raised when a file cannot be parsed as a valid Excel workbook
    (corrupted file, unsupported format, or no readable sheets).
    """
