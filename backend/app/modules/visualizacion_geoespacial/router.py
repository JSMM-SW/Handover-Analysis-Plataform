from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.shared.db.database import get_db
from .repository import GeoespacialRepository
from .schemas import ExecutionSummary, MapData
from .services import prepare_map

router = APIRouter(prefix="/geoespacial", tags=["Geoespacial"])


def get_repository(db: Session = Depends(get_db)):
    # Do not expose database connection details in HTTP error responses.
    try:
        yield GeoespacialRepository(db)
    except SQLAlchemyError:
        raise HTTPException(503, "No se pudo consultar la base de datos. Revisa la conexión del backend.") from None


@router.get("/ejecuciones", response_model=list[ExecutionSummary])
def executions(repository=Depends(get_repository)):
    return repository.executions()


@router.get("/ejecuciones/{execution_id}/hojas", response_model=list[str])
def sheets(execution_id: UUID, repository=Depends(get_repository)):
    if repository.execution(execution_id) is None:
        raise HTTPException(404, "La ejecución no existe.")
    return repository.sheets(execution_id)


@router.get("/mediciones", response_model=MapData)
def measurements(
    execution_id: UUID,
    hoja: str = Query(min_length=1),
    desde: datetime | None = None,
    hasta: datetime | None = None,
    tecnologia: int | None = Query(default=None, ge=0, le=1),
    cell_id: int | None = Query(default=None, gt=0),
    bbox: str | None = Query(default=None, description="oeste,sur,este,norte en grados"),
    repository=Depends(get_repository),
):
    for value in (desde, hasta):
        if value is not None and value.utcoffset() is None:
            raise HTTPException(422, "Las fechas deben incluir zona horaria, por ejemplo -05:00.")
    if desde and hasta and desde > hasta:
        raise HTTPException(422, "La fecha inicial debe ser anterior o igual a la final.")
    bounds = None
    if bbox is not None:
        try:
            bounds = tuple(float(part) for part in bbox.split(","))
            if len(bounds) != 4 or not (
                -180 <= bounds[0] < bounds[2] <= 180
                and -90 <= bounds[1] < bounds[3] <= 90
            ):
                raise ValueError
        except ValueError:
            raise HTTPException(422, "Zona inválida: usa oeste,sur,este,norte.") from None
    if repository.execution(execution_id) is None:
        raise HTTPException(404, "La ejecución no existe.")
    if hoja not in repository.sheets(execution_id):
        raise HTTPException(404, "La hoja no existe en esta ejecución.")
    records = repository.measurements(execution_id, hoja, desde, hasta)
    try:
        return prepare_map(records, tecnologia, cell_id, bounds)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
