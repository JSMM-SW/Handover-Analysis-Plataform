"""Orquesta las etapas puras del pipeline ETL (Extract -> Validate -> Clean ->
Normalize -> Structure). No conoce la base de datos ni el Repository: solo
recibe una ruta de archivo y devuelve los registros listos para persistir.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.etl.cleaner import deduplicate, validate_ranges
from app.etl.constants import MOTIVO_DUPLICADO, RSRP_STRONG_SIGNAL_THRESHOLD
from app.etl.extractor import extract_basic_info, extract_records, validate_required_columns
from app.etl.normalizer import normalize_record
from app.etl.transformer import structure_record
from app.etl.validator import validate_record

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
