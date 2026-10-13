import logging
import uuid as uuid_module

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.shared.config import Settings, get_settings
from app.shared.db.database import get_db
from app.shared.exceptions import (
    DuplicateFileError,
    ExtractionError,
    FileValidationError,
    SchemaValidationError,
)
from app.shared.file_utils import filename_key
from app.modules.ingesta.repository import HandoverRepository
from app.modules.ingesta.schemas import (
    CancelResponse,
    ProcessRequest,
    ProcessResult,
    StatusResponse,
    UploadBatchItem,
    UploadResponse,
)
from app.modules.ingesta import services
from app.modules.ingesta.services import (
    IncompleteUploadError,
    ensure_not_already_loaded,
    execute_ingestion,
    expire_stale_executions,
    export_valid_records_csv,
    handle_upload_stream,
    request_cancellation,
    start_ingestion,
)

logger = logging.getLogger(__name__)


def _on_startup() -> None:
    # Ejecuciones interrumpidas -> failed, y limpieza de temporales. Se resuelve
    # por atributo en cada arranque para que los tests puedan sustituirlo.
    services.startup_maintenance(get_settings())


router = APIRouter(prefix="/ingestion", tags=["Ingesta"], on_startup=[_on_startup])


_DUPLICATE_CODES = {"duplicado", "duplicado_en_seleccion"}


@router.post("/upload", response_model=list[UploadBatchItem])
def upload_files(
    response: Response,
    files: list[UploadFile] = File(...),
    declared_sizes: list[int] | None = Form(None),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> list[UploadBatchItem]:
    """Recibe uno o más archivos. Cada uno se valida y almacena de forma
    independiente: un archivo inválido no impide que los demás se procesen.

    Antes de guardar nada se rechaza (error_code "duplicado") un archivo cuyo
    nombre original ya tiene una ejecución completed/processing, y
    ("duplicado_en_seleccion") un nombre repetido dentro de la misma carga.
    El resultado es por archivo; si TODOS los archivos se rechazaron por
    duplicado, la respuesta es 409 (con la misma lista en el cuerpo).

    `declared_sizes` (opcional, un entero por archivo y en el mismo orden) es
    el tamaño en bytes que el cliente dice enviar: si no coincide con lo
    recibido, ese archivo se rechaza con error_code "subida_incompleta".
    """
    if declared_sizes is not None and len(declared_sizes) != len(files):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="declared_sizes debe traer un tamaño por cada archivo.",
        )
    repository = HandoverRepository(db)
    results: list[UploadBatchItem] = []
    seen_keys: set[str] = set()
    for index, file in enumerate(files):
        original_filename = file.filename or ""
        key = filename_key(original_filename)
        if original_filename and key in seen_keys:
            results.append(
                UploadBatchItem(
                    original_filename=original_filename,
                    ok=False,
                    error=f"El archivo '{original_filename}' está repetido en esta selección; "
                    "solo se procesa una vez.",
                    error_code="duplicado_en_seleccion",
                )
            )
            continue
        seen_keys.add(key)
        try:
            if original_filename:
                ensure_not_already_loaded(original_filename, repository, settings)
            # file.file es el temporal donde Starlette ya recibió la subida
            # (en disco si es grande): se copia por bloques, sin read() completo.
            upload_response = handle_upload_stream(
                original_filename,
                file.file,
                file.size,
                settings,
                declared_size=declared_sizes[index] if declared_sizes is not None else None,
            )
            results.append(
                UploadBatchItem(original_filename=original_filename, ok=True, upload=upload_response)
            )
        except DuplicateFileError as exc:
            results.append(
                UploadBatchItem(
                    original_filename=original_filename, ok=False, error=str(exc), error_code="duplicado"
                )
            )
        except IncompleteUploadError as exc:
            results.append(
                UploadBatchItem(
                    original_filename=original_filename,
                    ok=False,
                    error=str(exc),
                    error_code="subida_incompleta",
                )
            )
        except (FileValidationError, ExtractionError, SchemaValidationError) as exc:
            results.append(
                UploadBatchItem(
                    original_filename=original_filename, ok=False, error=str(exc), error_code="invalido"
                )
            )
    if results and all(item.error_code in _DUPLICATE_CODES for item in results):
        response.status_code = status.HTTP_409_CONFLICT
    return results


@router.post("/process", response_model=ProcessResult, status_code=status.HTTP_202_ACCEPTED)
def process_file(
    payload: ProcessRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> ProcessResult:
    """Crea la ejecución y devuelve de inmediato (202, status "processing").
    El pipeline y la carga corren en segundo plano: con archivos de ~86k
    filas la petición ya no queda abierta minutos. El cliente hace polling
    a GET /status/{execution_id} hasta que el estado sea completed o failed.
    """
    repository = HandoverRepository(db)

    try:
        result = start_ingestion(payload, settings, repository)
    except DuplicateFileError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except FileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    background_tasks.add_task(
        execute_ingestion, uuid_module.UUID(result.execution_id), payload, settings
    )
    return result


@router.get("/status/{execution_id}", response_model=StatusResponse)
def get_status(
    execution_id: str,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> StatusResponse:
    try:
        parsed_id = uuid_module.UUID(execution_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="execution_id no es un UUID válido."
        )

    repository = HandoverRepository(db)
    # Si el servidor se reinició a mitad del proceso, la ejecución dejó de
    # latir: se marca "failed" (interrumpida) aquí, en vez de quedar en
    # "processing" para siempre.
    expire_stale_executions(repository, settings, parsed_id)
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
        etapa=execution.etapa,
        progreso=execution.progreso,
        cancel_requested=execution.cancel_requested,
        updated_at=execution.updated_at,
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


@router.post(
    "/cancel/{execution_id}", response_model=CancelResponse, status_code=status.HTTP_202_ACCEPTED
)
def cancel_execution(
    execution_id: str,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> CancelResponse:
    """Cancelación cooperativa de una ejecución en curso: el pipeline revisa
    la bandera entre etapas y entre lotes de COPY, hace rollback total (0
    filas, sin consumir número de sesión), borra el archivo temporal y deja
    la ejecución "cancelled" (el nombre del archivo queda libre).

    202: cancelación solicitada (seguir consultando /status). 404: no existe.
    409: la ejecución ya terminó ("ya completada" si el commit ya ocurrió: no
    se deshace nada).
    """
    try:
        parsed_id = uuid_module.UUID(execution_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="execution_id no es un UUID válido."
        )

    try:
        result = request_cancellation(parsed_id, HandoverRepository(db), settings)
    except FileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe una ejecución con id {execution_id}.",
        )
    return result


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
