from datetime import datetime, time
from uuid import UUID
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError, TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session

from app.shared.db.database import get_db
from .repository import GeoespacialRepository
from .schemas import ExecutionSummary, MapData, Measurement, HandoverEvent
from .services import prepare_map
from .rendering import render_map
from .analysis_cache import analysis_cache

router = APIRouter(prefix="/geoespacial", tags=["Geoespacial"])
logger = logging.getLogger(__name__)


def parse_bounds(value):
    if value is None:
        return None
    try:
        bounds = tuple(float(part) for part in value.split(','))
        if len(bounds) != 4 or not (-180 <= bounds[0] < bounds[2] <= 180 and -90 <= bounds[1] < bounds[3] <= 90):
            raise ValueError
        return bounds
    except ValueError:
        raise HTTPException(422, 'Zona inválida: usa oeste,sur,este,norte.') from None


def get_repository(db: Session = Depends(get_db)):
    # Do not expose database connection details in HTTP error responses.
    try:
        yield GeoespacialRepository(db)
    except SQLAlchemyError as error:
        state = getattr(getattr(error, 'orig', None), 'sqlstate', None)
        logger.error('Geoespacial: error de lectura; tipo=%s SQLSTATE=%s conexión_invalidada=%s',
                     type(error).__name__, state or 'sin código', getattr(error, 'connection_invalidated', False))
        if state == '57014':
            raise HTTPException(504, 'La consulta superó el tiempo de espera de la base de datos. Vuelve a intentarlo o selecciona un intervalo menor.') from None
        if isinstance(error, PoolTimeoutError):
            raise HTTPException(503, 'El backend está ocupado con otras consultas. Espera unos instantes y vuelve a intentar.') from None
        raise HTTPException(503, "No se pudo consultar la base de datos. Revisa la conexión del backend.") from None


@router.get("/ejecuciones", response_model=list[ExecutionSummary])
def executions(repository=Depends(get_repository)):
    return repository.executions()


@router.get("/ejecuciones/{execution_id}/hojas", response_model=list[str | None])
def sheets(execution_id: UUID, repository=Depends(get_repository)):
    if repository.execution(execution_id) is None:
        raise HTTPException(404, "La ejecución no existe.")
    return repository.sheets(execution_id)


@router.get("/mediciones", response_model=MapData)
def measurements(
    execution_id: list[UUID] = Query(min_length=1),
    hoja: str | None = Query(default=None, min_length=1),
    desde: datetime | None = None,
    hasta: datetime | None = None,
    hora_inicio: time | None = None,
    hora_fin: time | None = None,
    tecnologia: int | None = Query(default=None, ge=0, le=3),
    cell_id: int | None = Query(default=None, gt=0),
    bbox: str | None = Query(default=None, description="oeste,sur,este,norte en grados"),
    vista_bbox: str | None = Query(default=None, description="Ventana de dibujo; no modifica los totales"),
    zoom: int | None = Query(default=None, ge=0, le=22),
    repository=Depends(get_repository),
):
    for value in (desde, hasta):
        if value is not None and value.utcoffset() is None:
            raise HTTPException(422, "Las fechas deben incluir zona horaria, por ejemplo -05:00.")
    if desde and hasta and desde > hasta:
        raise HTTPException(422, "La fecha inicial debe ser anterior o igual a la final.")
    if hora_inicio and hora_fin and hora_inicio > hora_fin:
        raise HTTPException(422, "La hora inicial debe ser anterior o igual a la final.")
    bounds = parse_bounds(bbox)
    viewport = parse_bounds(vista_bbox)
    execution_ids = list(dict.fromkeys(execution_id))
    executions = [repository.execution(key) for key in execution_ids]
    if any(execution is None for execution in executions):
        raise HTTPException(404, "La ejecución no existe.")
    if hoja is not None and not any(hoja in repository.sheets(key) for key in execution_ids):
        raise HTTPException(404, "La hoja no existe en esta ejecución.")
    key = (tuple(execution_ids), tuple((getattr(row, 'records_valid', None), str(getattr(row, 'processing_date', ''))) for row in executions),
           hoja, desde, hasta, hora_inicio, hora_fin, tecnologia, cell_id, bounds)

    def analyze():
        records = repository.measurements(execution_ids, hoja, desde, hasta)
        return prepare_map(records, tecnologia, cell_id, bounds, desde=desde,
                           hora_inicio=hora_inicio, hora_fin=hora_fin,
                           detected_events=repository.handovers(execution_ids))

    try:
        data = analysis_cache.get_or_load(key, analyze)
        return render_map(data, zoom=zoom, bounds=viewport)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/mediciones/{record_id}', response_model=Measurement)
def measurement_detail(record_id: UUID, repository=Depends(get_repository)):
    row = repository.measurement(record_id)
    if row is None:
        raise HTTPException(404, 'La medición no existe.')
    if row.latitud is None or row.longitud is None:
        raise HTTPException(422, 'La medición no tiene ubicación.')
    return Measurement.model_validate(row)


@router.get('/handovers/{record_id}', response_model=HandoverEvent)
def handover_detail(record_id: UUID, repository=Depends(get_repository)):
    row = repository.measurement(record_id)
    if row is None:
        raise HTTPException(404, 'La medición no existe.')
    # Validate the session version so details can reuse its cached detection.
    if repository.execution(row.execution_id) is None:
        raise HTTPException(404, 'La ejecución no existe.')
    event = next((event for event in repository.handovers([row.execution_id])
                  if event.medicion_posterior_id == str(record_id)), None)
    if event is None:
        raise HTTPException(404, 'La medición no corresponde a un handover.')
    measurement = measurement_detail(record_id, repository)
    return HandoverEvent(**measurement.model_dump(), registro_anterior_id=event.medicion_previa_id,
                         celda_origen=event.celda_origen_cid, nodo_origen=event.celda_origen_node_id)


@router.get("/disponibilidad")
def availability(execution_id: list[UUID] = Query(min_length=1), repository=Depends(get_repository)):
    execution_ids = list(dict.fromkeys(execution_id))
    if any(repository.execution(key) is None for key in execution_ids):
        raise HTTPException(404, "La ejecución no existe.")
    return repository.available_days(execution_ids)
