import logging
import uuid as uuid_module

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.exceptions import ExtractionError, FileValidationError, SchemaValidationError
from app.repositories.data_repository import HandoverRepository
from app.schemas.ingestion import ProcessRequest, ProcessResult, StatusResponse, UploadResponse
from app.services.ingestion_service import handle_upload, run_ingestion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> UploadResponse:
    content = await file.read()

    try:
        return handle_upload(file.filename or "", content, settings)
    except FileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (ExtractionError, SchemaValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


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
