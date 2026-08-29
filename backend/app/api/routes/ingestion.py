import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.config import Settings, get_settings
from app.core.exceptions import ExtractionError, FileValidationError
from app.schemas.ingestion import UploadResult
from app.services.ingestion_service import process_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/upload", response_model=UploadResult)
async def upload_file(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> UploadResult:
    content = await file.read()

    try:
        return process_upload(file.filename or "", content, settings)
    except FileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
