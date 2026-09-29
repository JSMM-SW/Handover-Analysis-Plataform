from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExecutionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    execution_id: UUID
    filename: str
    processing_date: datetime
    records_valid: int
    status: str
    fecha_inicio: datetime | None = None
    fecha_fin: datetime | None = None


class Measurement(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_registro: UUID
    execution_id: UUID | None = None
    timestamp_medicion: datetime
    latitud: float
    longitud: float
    cell_id: int
    tecnologia: int
    rsrp_dbm: int | None
    hoja_origen: str | None
    node_id: int | None = None
    psc_pci: int | None = None
    earfcn: int | None = None
    tac: int | None = None
    rssi: int | None = None
    rsrq: int | None = None
    rssnr: int | None = None
    accuracy: int | None = None
    velocidad_kmh: float | None = None


class HandoverEvent(Measurement):
    registro_anterior_id: UUID
    celda_origen: int
    nodo_origen: int


class RadioBaseEstimate(BaseModel):
    id: str
    execution_id: UUID
    hoja_origen: str | None
    node_id: int
    cell_id: int
    tecnologia: int
    earfcn: int
    tac: int | None
    psc_pci: list[int]
    latitud: float
    longitud: float
    mediciones_validas: int
    posiciones_disponibles: int
    posiciones_utilizadas: int
    rssi_max: float
    dispersion_m: float


class RadioBaseSummary(BaseModel):
    metodo: str = 'Centroide ponderado por RSSI y precisión GPS'
    grupos_evaluados: int = 0
    grupos_insuficientes: int = 0
    mediciones_descartadas: int = 0
    duplicados_descartados: int = 0
    motivos: dict[str, int] = Field(default_factory=dict)
    parametros: dict[str, float] = Field(default_factory=dict)


class MapData(BaseModel):
    mediciones: list[Measurement]
    tramos: list[list[UUID]]
    total: int
    handovers: list[HandoverEvent]
    total_handovers: int
    advertencias: list[str]
    radios_base: list[RadioBaseEstimate] = Field(default_factory=list)
    resumen_radios_base: RadioBaseSummary = Field(default_factory=RadioBaseSummary)
