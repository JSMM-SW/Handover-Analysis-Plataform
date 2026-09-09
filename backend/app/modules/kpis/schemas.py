from datetime import date
from pydantic import BaseModel, Field

class SignalMetricsResponse(BaseModel):
    fecha: date
    total_mediciones: int = Field(description="Total de mediciones de RSRP válidas procesadas")
    promedio_rsrp: float = Field(description="Nivel promedio de señal RSRP en dBm")
    eventos_criticos: int = Field(description="Mediciones con señal severamente degradada (<-110 dBm)")
    tasa_riesgo: float = Field(description="Porcentaje de mediciones en estado crítico")

class HandoverKpiResponse(BaseModel):
    fecha: date
    total_handovers: int = Field(description="Cantidad de saltos entre antenas distintas")
    ping_pongs: int = Field(description="Handovers ineficientes (A -> B -> A)")
    tasa_hopp: float = Field(description="Porcentaje de Ping-Pong sobre el total de handovers (%)")

class KpiSummaryResponse(BaseModel):
    fecha_inicio: date
    fecha_fin: date
    total_handovers: int = Field(description="Total de saltos en el periodo")
    exitosos: int
    fallidos: int
    hor_porcentaje: float = Field(description="Handover Success Rate (%)")
    tasa_fallos: float = Field(description="Handover Failure Rate (%)")
    ping_pongs: int
    tasa_hopp: float = Field(description="Ping-Pong Rate (%)")
    uho_eventos: int = Field(description="Handovers Innecesarios")
    tasa_uho: float = Field(description="Unnecessary Handover Rate (%)")

class HourlyDistributionResponse(BaseModel):
    hora: int = Field(description="Hora del día (0-23)")
    cantidad_handovers: int = Field(description="Número de saltos en esa hora")

class DailyTrendResponse(BaseModel):
    fecha_etiqueta: str = Field(description="Fecha en formato corto (ej. 01/05)")
    hor_porcentaje: float = Field(description="Tasa de éxito del día")
    tasa_fallos: float = Field(description="Tasa de fallos del día")