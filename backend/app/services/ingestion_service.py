import logging
import time
import uuid
from datetime import datetime, timezone

from app.core.config import Settings
from app.etl.extractor import extract_basic_info
from app.etl.validator import validate_uploaded_file
from app.schemas.ingestion import UploadResult
from app.utils.file_utils import sanitize_filename

logger = logging.getLogger(__name__)


def process_upload(filename: str, content: bytes, settings: Settings) -> UploadResult:
    execution_id = str(uuid.uuid4())
    started_at = time.perf_counter()
    logger.info("[%s] Carga recibida: '%s' (%d bytes)", execution_id, filename, len(content))

    validate_uploaded_file(filename, content, settings)

    stored_filename = f"{execution_id}_{sanitize_filename(filename)}"
    destination = settings.resolved_data_input_dir() / stored_filename
    destination.write_bytes(content)
    logger.info("[%s] Archivo almacenado en '%s'", execution_id, destination)

    sheets = extract_basic_info(destination, execution_id)

    processing_time = time.perf_counter() - started_at
    logger.info(
        "[%s] Extracción básica completada: %d hoja(s) en %.3fs",
        execution_id,
        len(sheets),
        processing_time,
    )

    return UploadResult(
        execution_id=execution_id,
        original_filename=filename,
        stored_filename=stored_filename,
        file_size_bytes=len(content),
        upload_timestamp=datetime.now(timezone.utc),
        sheets=sheets,
        processing_time_seconds=round(processing_time, 3),
        status="success",
    )
