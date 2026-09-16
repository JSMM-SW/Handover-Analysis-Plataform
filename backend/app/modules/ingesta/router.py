import logging
import uuid as uuid_module

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.shared.config import Settings, get_settings
from app.shared.db.database import get_db
from app.shared.exceptions import ExtractionError, FileValidationError, SchemaValidationError
from app.modules.ingesta.repository import HandoverRepository
from app.modules.ingesta.schemas import (
    ProcessRequest,
    ProcessResult,
    StatusResponse,
    UploadBatchItem,
    UploadResponse,
)
from app.modules.ingesta.services import export_valid_records_csv, handle_upload, run_ingestion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion", tags=["Ingesta"])


@router.post("/upload", response_model=list[UploadBatchItem])
async def upload_files(
    files: list[UploadFile] = File(...),
    settings: Settings = Depends(get_settings),
) -> list[UploadBatchItem]:
    """Recibe uno o más archivos. Cada uno se valida y almacena de forma
    independiente: un archivo inválido no impide que los demás se procesen.
    """
    results: list[UploadBatchItem] = []
    for file in files:
        original_filename = file.filename or ""
        content = await file.read()
        try:
            upload_response = handle_upload(original_filename, content, settings)
            results.append(
                UploadBatchItem(original_filename=original_filename, ok=True, upload=upload_response)
            )
        except FileValidationError as exc:
            results.append(
                UploadBatchItem(original_filename=original_filename, ok=False, error=str(exc))
            )
        except (ExtractionError, SchemaValidationError) as exc:
            results.append(
                UploadBatchItem(original_filename=original_filename, ok=False, error=str(exc))
            )
    return results


@router.post("/process", response_model=ProcessResult)
def process_file(
    payload: ProcessRequest,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> ProcessResult:
    repository = HandoverRepository(db)

    try:
        return run_ingestion(payload, settings, repository)
    except FileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/status/{execution_id}", response_model=StatusResponse)
def get_status(
    execution_id: str,
    db: Session = Depends(get_db),
) -> StatusResponse:
    try:
        parsed_id = uuid_module.UUID(execution_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="execution_id no es un UUID válido."
        )

    repository = HandoverRepository(db)
    execution = repository.get_execution(parsed_id)
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe una ejecución con id {execution_id}.",
        )

    return StatusResponse(
        execution_id=str(execution.execution_id),
        sesion_label=execution.sesion_label,
        filename=execution.filename,
        status=execution.status,
        processing_date=execution.processing_date,
        records_read=execution.records_read,
        records_valid=execution.records_valid,
        records_rejected=execution.records_rejected,
        warnings=execution.warnings,
        errors=execution.errors,
        processing_time_seconds=(
            float(execution.processing_time_seconds)
            if execution.processing_time_seconds is not None
            else None
        ),
    )


@router.get("/export")
def export_dataset(
    execution_id: str | None = None,
    sesion_label: int | None = None,
    db: Session = Depends(get_db),
) -> Response:
    """Descarga el dataset limpio (handover_record) en CSV. Nunca incluye
    handover_record_rejected. Sin filtro, exporta todo el dataset válido.

    Filtros mutuamente excluyentes: si se da `execution_id`, tiene
    precedencia sobre `sesion_label` (el identificador amigable que van a
    usar los demás componentes del TIC).
    """
    repository = HandoverRepository(db)

    resolved_execution_id = None
    filename_suffix = "completo"

    if execution_id is not None:
        try:
            resolved_execution_id = uuid_module.UUID(execution_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="execution_id no es un UUID válido.",
            )
        filename_suffix = execution_id
    elif sesion_label is not None:
        resolved_execution_id = repository.get_execution_id_by_sesion_label(sesion_label)
        if resolved_execution_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No existe una ejecución con sesion_label {sesion_label}.",
            )
        filename_suffix = f"sesion_{sesion_label}"

    csv_content = export_valid_records_csv(repository, resolved_execution_id)

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="handover_record_{filename_suffix}.csv"'
        },
    )
