import csv
import io
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.shared.config import Settings
from app.shared.exceptions import ExtractionError, FileValidationError, SchemaValidationError
from app.shared.file_utils import sanitize_filename
from app.modules.ingesta.etl.cleaner import apply_sentinels_csv, deduplicate, validate_ranges
from app.modules.ingesta.etl.constants import (
    DEDUP_KEY_CSV,
    DEDUP_KEY_XLSX,
    MOTIVO_DUPLICADO,
    MOTIVO_GPS_SIN_FIX,
    MOTIVO_GPS_SIN_FIX_CSV,
    ORIGEN_CSV,
    ORIGEN_XLSX,
    RSRP_STRONG_SIGNAL_THRESHOLD,
)
from app.modules.ingesta.etl.extractor import (
    detect_format,
    extract_basic_info,
    extract_csv_preview,
    extract_records_csv,
    extract_records_xlsx,
    validate_required_columns_csv,
    validate_required_columns_xlsx,
)
from app.modules.ingesta.etl.normalizer import (
    normalize_record,
    normalize_record_csv,
    normalize_sys_time,
    normalize_timestamp,
)
from app.modules.ingesta.etl.transformer import structure_record
from app.modules.ingesta.etl.validator import (
    validate_record_csv,
    validate_record_xlsx,
    validate_uploaded_file,
)
from app.modules.ingesta.etl.velocity import compute_velocities
from app.modules.ingesta.repository import HandoverRepository
from app.modules.ingesta.schemas import ProcessRequest, ProcessResult, UploadResponse

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    records_read: int
    valid_records: list[dict] = field(default_factory=list)
    rejected_records: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _build_rejected(record: dict, motivo: str, datos_crudos: dict | None = None) -> dict:
    return {
        "hoja_origen": record["hoja_origen"],
        "fila_excel": record["fila_excel"],
        "motivo_rechazo": motivo,
        "datos_crudos": record["data"] if datos_crudos is None else datos_crudos,
    }


def _run_pipeline_xlsx(path: Path, archivo_origen: str, execution_id: str) -> PipelineResult:
    sheets = extract_basic_info(path, execution_id)
    validate_required_columns_xlsx(sheets, execution_id)

    raw_records = extract_records_xlsx(path, execution_id)

    rejected: list[dict] = []
    candidates: list[dict] = []

    for record in raw_records:
        motivo = validate_record_xlsx(record["data"]) or validate_ranges(record["data"])
        if motivo:
            rejected.append(_build_rejected(record, motivo))
        else:
            candidates.append(record)

    unique, duplicates = deduplicate(candidates, DEDUP_KEY_XLSX)
    rejected.extend(_build_rejected(record, MOTIVO_DUPLICADO) for record in duplicates)

    valid_records: list[dict] = []
    strong_signal_count = 0
    for record in unique:
        normalized = normalize_record(record["data"])
        if normalized["rsrp_dbm"] > RSRP_STRONG_SIGNAL_THRESHOLD:
            strong_signal_count += 1
        valid_records.append(
            structure_record(normalized, record["hoja_origen"], archivo_origen, ORIGEN_XLSX)
        )

    warnings: list[str] = []
    if strong_signal_count:
        warnings.append(
            f"{strong_signal_count} registro(s) con RSRP > {RSRP_STRONG_SIGNAL_THRESHOLD} dBm "
            "(señal inusualmente fuerte, conservados)"
        )

    gps_reject_anchors = [
        (
            normalize_timestamp(r["datos_crudos"]["Fecha"], r["datos_crudos"]["Hora"]),
            r["hoja_origen"],
        )
        for r in rejected
        if r["motivo_rechazo"] == MOTIVO_GPS_SIN_FIX
    ]
    warnings.extend(compute_velocities(valid_records, gps_reject_anchors))

    logger.info(
        "[%s] Pipeline xlsx: %d leídos, %d válidos, %d rechazados",
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


def _run_pipeline_csv(path: Path, archivo_origen: str, execution_id: str) -> PipelineResult:
    sheets = extract_csv_preview(path, execution_id)
    validate_required_columns_csv(sheets, execution_id)

    raw_records = extract_records_csv(path, execution_id)

    rejected: list[dict] = []
    candidates: list[dict] = []
    nulled_field_counts: dict[str, int] = {}

    for record in raw_records:
        motivo = validate_record_csv(record["data"])
        if motivo:
            rejected.append(_build_rejected(record, motivo))
            continue

        cleaned_data, nulled_fields = apply_sentinels_csv(record["data"])
        for field_name in nulled_fields:
            nulled_field_counts[field_name] = nulled_field_counts.get(field_name, 0) + 1

        candidates.append(
            {
                "hoja_origen": record["hoja_origen"],
                "fila_excel": record["fila_excel"],
                "data": cleaned_data,
                "datos_crudos_originales": record["data"],
            }
        )

    unique, duplicates = deduplicate(candidates, DEDUP_KEY_CSV)
    rejected.extend(
        _build_rejected(record, MOTIVO_DUPLICADO, datos_crudos=record["datos_crudos_originales"])
        for record in duplicates
    )

    valid_records: list[dict] = []
    for record in unique:
        normalized = normalize_record_csv(record["data"])
        valid_records.append(
            structure_record(normalized, record["hoja_origen"], archivo_origen, ORIGEN_CSV)
        )

    warnings: list[str] = [
        f"{count} registro(s) csv con {field_name} = centinela (sin dato), guardado como NULL"
        for field_name, count in sorted(nulled_field_counts.items())
    ]

    gps_reject_anchors = [
        (normalize_sys_time(r["datos_crudos"]["sys_time"]), r["hoja_origen"])
        for r in rejected
        if r["motivo_rechazo"] == MOTIVO_GPS_SIN_FIX_CSV
    ]
    warnings.extend(compute_velocities(valid_records, gps_reject_anchors))

    logger.info(
        "[%s] Pipeline csv: %d leídos, %d válidos, %d rechazados",
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


def run_pipeline(path: Path, archivo_origen: str, execution_id: str) -> PipelineResult:
    """Orquesta las etapas puras del pipeline ETL (Extract -> Validate -> Clean
    -> Normalize -> Structure) para el formato detectado a partir del nombre
    del archivo. No conoce la base de datos ni el Repository: solo recibe una
    ruta de archivo y devuelve los registros listos para persistir.
    """
    if detect_format(archivo_origen) == ORIGEN_CSV:
        return _run_pipeline_csv(path, archivo_origen, execution_id)
    return _run_pipeline_xlsx(path, archivo_origen, execution_id)


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

    if detect_format(filename) == ORIGEN_CSV:
        sheets = extract_csv_preview(destination, upload_id)
        validate_required_columns_csv(sheets, upload_id)
    else:
        sheets = extract_basic_info(destination, upload_id)
        validate_required_columns_xlsx(sheets, upload_id)

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
    sesion_label = repository.get_execution(execution_id).sesion_label
    logger.info(
        "[%s] Ejecución creada para '%s' (sesión #%s)",
        execution_id,
        payload.original_filename,
        sesion_label,
    )

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
            sesion_label=sesion_label,
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
            sesion_label=sesion_label,
            filename=payload.original_filename,
            records_read=0,
            records_valid=0,
            records_rejected=0,
            warnings=[],
            errors=[str(exc)],
            processing_time_seconds=processing_time,
            status="failed",
        )


_EXPORT_COLUMNS = [
    "id_registro",
    "execution_id",
    "timestamp_medicion",
    "cell_id",
    "tac",
    "earfcn",
    "tecnologia",
    "latitud",
    "longitud",
    "rsrp_dbm",
    "node_id",
    "psc_pci",
    "rssi",
    "rsrq",
    "rssnr",
    "accuracy",
    "velocidad_kmh",
    "archivo_origen",
    "hoja_origen",
    "origen_formato",
    "created_at",
]


def export_valid_records_csv(
    repository: HandoverRepository, execution_id: uuid.UUID | None = None
) -> str:
    """Exporta `handover_record` (nunca handover_record_rejected) a CSV.

    Sin `execution_id`, exporta el dataset completo (todas las ejecuciones).
    """
    records = repository.get_valid_records(execution_id)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_EXPORT_COLUMNS)
    for record in records:
        writer.writerow([getattr(record, column) for column in _EXPORT_COLUMNS])

    return buffer.getvalue()
