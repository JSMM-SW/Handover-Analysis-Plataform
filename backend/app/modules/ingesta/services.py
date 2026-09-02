import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.shared.config import Settings
from app.shared.exceptions import ExtractionError, FileValidationError, SchemaValidationError
from app.shared.file_utils import sanitize_filename
from app.modules.ingesta.etl.cleaner import deduplicate, validate_ranges
from app.modules.ingesta.etl.constants import MOTIVO_DUPLICADO, RSRP_STRONG_SIGNAL_THRESHOLD
from app.modules.ingesta.etl.extractor import (
    extract_basic_info,
    extract_records,
    validate_required_columns,
)
from app.modules.ingesta.etl.normalizer import normalize_record
from app.modules.ingesta.etl.transformer import structure_record
from app.modules.ingesta.etl.validator import validate_record, validate_uploaded_file
from app.modules.ingesta.repository import HandoverRepository
from app.modules.ingesta.schemas import ProcessRequest, ProcessResult, UploadResponse

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    records_read: int
    valid_records: list[dict] = field(default_factory=list)
    rejected_records: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _build_rejected(record: dict, motivo: str) -> dict:
    return {
        "hoja_origen": record["hoja_origen"],
        "fila_excel": record["fila_excel"],
        "motivo_rechazo": motivo,
        "datos_crudos": record["data"],
    }


def run_pipeline(path: Path, archivo_origen: str, execution_id: str) -> PipelineResult:
    """Orquesta las etapas puras del pipeline ETL (Extract -> Validate -> Clean
    -> Normalize -> Structure). No conoce la base de datos ni el Repository:
    solo recibe una ruta de archivo y devuelve los registros listos para
    persistir.
    """
    sheets = extract_basic_info(path, execution_id)
    validate_required_columns(sheets, execution_id)

    raw_records = extract_records(path, execution_id)

    rejected: list[dict] = []
    candidates: list[dict] = []

    for record in raw_records:
        motivo = validate_record(record["data"]) or validate_ranges(record["data"])
        if motivo:
            rejected.append(_build_rejected(record, motivo))
        else:
            candidates.append(record)

    unique, duplicates = deduplicate(candidates)
    rejected.extend(_build_rejected(record, MOTIVO_DUPLICADO) for record in duplicates)

    valid_records: list[dict] = []
    strong_signal_count = 0
    for record in unique:
        normalized = normalize_record(record["data"])
        if normalized["rsrp_dbm"] > RSRP_STRONG_SIGNAL_THRESHOLD:
            strong_signal_count += 1
        valid_records.append(
            structure_record(normalized, record["hoja_origen"], archivo_origen)
        )

    warnings: list[str] = []
    if strong_signal_count:
        warnings.append(
            f"{strong_signal_count} registro(s) con RSRP > {RSRP_STRONG_SIGNAL_THRESHOLD} dBm "
            "(señal inusualmente fuerte, conservados)"
        )

    logger.info(
        "[%s] Pipeline: %d leídos, %d válidos, %d rechazados",
        execution_id,
        len(raw_records),
        len(valid_records),
        len(rejected),
    )

    return PipelineResult(
        records_read=len(raw_records),
        valid_records=valid_records,
        rejected_records=rejected,
        warnings=warnings,
    )


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
