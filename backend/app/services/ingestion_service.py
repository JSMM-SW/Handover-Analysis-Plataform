import logging
import time
import uuid
from datetime import datetime, timezone

from app.core.config import Settings
from app.core.exceptions import ExtractionError, FileValidationError, SchemaValidationError
from app.etl.extractor import extract_basic_info, validate_required_columns
from app.etl.validator import validate_uploaded_file
from app.repositories.data_repository import HandoverRepository
from app.schemas.ingestion import ProcessRequest, ProcessResult, UploadResponse
from app.services.etl_service import run_pipeline
from app.utils.file_utils import sanitize_filename

logger = logging.getLogger(__name__)


def handle_upload(filename: str, content: bytes, settings: Settings) -> UploadResponse:
    """Recibe el archivo, lo valida a nivel de archivo, lo guarda y confirma
    que su estructura (columnas requeridas) es la esperada. No crea todavía
    una ejecución en base de datos ni aplica reglas de negocio por registro.
    """
    upload_id = str(uuid.uuid4())
    logger.info("[%s] Carga recibida: '%s' (%d bytes)", upload_id, filename, len(content))

    validate_uploaded_file(filename, content, settings)

    stored_filename = f"{upload_id}_{sanitize_filename(filename)}"
    destination = settings.resolved_data_input_dir() / stored_filename
    destination.write_bytes(content)
    logger.info("[%s] Archivo almacenado en '%s'", upload_id, destination)

    sheets = extract_basic_info(destination, upload_id)
    validate_required_columns(sheets, upload_id)

    return UploadResponse(
        upload_id=upload_id,
        original_filename=filename,
        stored_filename=stored_filename,
        file_size_bytes=len(content),
        upload_timestamp=datetime.now(timezone.utc),
        sheets=sheets,
        status="uploaded",
    )


def run_ingestion(
    payload: ProcessRequest, settings: Settings, repository: HandoverRepository
) -> ProcessResult:
    """Corre el pipeline ETL completo sobre un archivo ya subido y persiste
    el resultado (registros válidos, rechazados y el resumen de ejecución).
    """
    started_at = time.perf_counter()
    path = settings.resolved_data_input_dir() / payload.stored_filename

    if not path.exists():
        raise FileValidationError(
            "El archivo cargado ya no está disponible en el servidor; vuelve a subirlo."
        )

    execution_id = repository.create_execution(filename=payload.original_filename)
    logger.info("[%s] Ejecución creada para '%s'", execution_id, payload.original_filename)

    try:
        pipeline_result = run_pipeline(path, payload.original_filename, str(execution_id))

        repository.save_valid_records(execution_id, pipeline_result.valid_records)
        repository.save_rejected_records(execution_id, pipeline_result.rejected_records)

        processing_time = round(time.perf_counter() - started_at, 3)
        repository.finish_execution(
            execution_id,
            records_read=pipeline_result.records_read,
            records_valid=len(pipeline_result.valid_records),
            records_rejected=len(pipeline_result.rejected_records),
            warnings=pipeline_result.warnings,
            errors=[],
            processing_time_seconds=processing_time,
        )

        return ProcessResult(
            execution_id=str(execution_id),
            filename=payload.original_filename,
            records_read=pipeline_result.records_read,
            records_valid=len(pipeline_result.valid_records),
            records_rejected=len(pipeline_result.rejected_records),
            warnings=pipeline_result.warnings,
            errors=[],
            processing_time_seconds=processing_time,
            status="completed",
        )
    except (ExtractionError, SchemaValidationError) as exc:
        processing_time = round(time.perf_counter() - started_at, 3)
        logger.warning("[%s] Ejecución fallida: %s", execution_id, exc)
        repository.finish_execution(
            execution_id,
            records_read=0,
            records_valid=0,
            records_rejected=0,
            warnings=[],
            errors=[str(exc)],
            processing_time_seconds=processing_time,
        )
        return ProcessResult(
            execution_id=str(execution_id),
            filename=payload.original_filename,
            records_read=0,
            records_valid=0,
            records_rejected=0,
            warnings=[],
            errors=[str(exc)],
            processing_time_seconds=processing_time,
            status="failed",
        )
