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


class DuplicateFileError(IngestionError):
    """Raised when a file with the same normalized original name already has
    an execution in "processing" or "completed" (HTTP 409). Failed or
    cancelled executions do not block the name.
    """


class LoadVerificationError(IngestionError):
    """Raised when, after the Load, the rows actually inserted for an
    execution do not match its records_valid/records_rejected counters. The
    whole Load is rolled back and the execution is marked "failed".
    """


class IngestionCancelled(Exception):
    """Raised inside the pipeline when the user requested cancellation
    (cooperative: checked between stages and between COPY batches). Not an
    IngestionError on purpose: it must never be handled as a failure.
    """


class SchemaValidationError(IngestionError):
    """Raised when a sheet does not contain the columns required to run the
    handover pipeline (structural mismatch, blocks the whole file — this is
    not a per-record rejection).
    """
