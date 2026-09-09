from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ExecutionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    execution_id: UUID
    filename: str
    processing_date: datetime
    records_valid: int
    status: str


class Measurement(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_registro: UUID
    timestamp_medicion: datetime
    latitud: float
    longitud: float
    cell_id: int
    tecnologia: int
    rsrp_dbm: int
    hoja_origen: str


class MapData(BaseModel):
    mediciones: list[Measurement]
    tramos: list[list[UUID]]
    total: int
    advertencias: list[str]
