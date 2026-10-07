"""Modelos de datos para las respuestas de los endpoints del módulo de KPIs."""
from datetime import date, datetime


from pydantic import BaseModel, Field
    


class SignalMetricsResponse(BaseModel):
    """Respuesta de GET /kpis/daily: calidad de señal general de un día
    puntual (no es específico de handovers)."""

    fecha: date
    total_mediciones: int = Field(description="Total de mediciones procesadas")
    promedio_rsrp: float | None = Field(description="RSRP promedio desde rsrp; null cuando no hay medidas")
    eventos_criticos: int | None = Field(description="Mediciones con señal severamente degradada (<-110 dBm)")
    tasa_riesgo: float | None = Field(description="Porcentaje de mediciones en estado crítico")


class SesionResponse(BaseModel):
    """Un elemento de la respuesta de GET /kpis/sesiones: una carga de
    archivo disponible para filtrar los demás endpoints por sesión."""

    sesion_label: int = Field(description="Identificador corto y amigable de la sesión (carga de archivo)")
    filename: str = Field(description="Nombre del archivo original que se cargó")
    processing_date: datetime = Field(description="Fecha y hora en que se procesó la carga")
    records_valid: int = Field(description="Registros válidos que aportó esta sesión a handover_record")


class KpiSummaryResponse(BaseModel):
    """Respuesta de GET /kpis/summary: resumen agregado de KPIs de handover
    para un rango de fechas (y, opcionalmente, una tecnología)."""

    fecha_inicio: date
    fecha_fin: date
    total_mediciones: int = Field(description="Total de mediciones tomadas en el periodo")
    total_handovers: int = Field(description="Total de saltos de celda detectados en el periodo")
    tasa_handover: float = Field(
        description="total_handovers / total_mediciones (%). Qué tan seguido ocurre un "
        "handover respecto al total de mediciones -- no es una tasa de éxito."
    )
    exitosos: int = Field(
        description="Handovers donde NO se cumplió el criterio PHD: rssi_destino > rssi_origen "
        "y rsrq_destino >= rsrq_origen -- la conexión mejoró o se mantuvo mejor"
    )
    fallidos: int = Field(
        description="Handovers donde SÍ se cumplió el criterio PHD: rssi_destino <= rssi_origen "
        "o rsrq_destino < rsrq_origen -- la conexión se degradó"
    )
    indeterminados: int = Field(
        description="Handovers sin RSSI/RSRQ disponibles en ambos lados de la "
        "transición -- no se pueden clasificar como éxito ni fallo"
    )
    tasa_exito: float = Field(
        description="exitosos / (exitosos + fallidos) (%). Los indeterminados quedan fuera "
        "del denominador a propósito, no hay evidencia para clasificarlos."
    )
    tasa_innecesarios: float = Field(
        description="uho_eventos / uho_evaluables (%), según el criterio UHO: el salto no hacía "
        "falta porque la señal de la celda de ORIGEN ya era buena (RSSI >= -100 dBm y "
        "RSRQ >= -15 dB). Es independiente de PHD/tasa_exito -- responde si el salto era "
        "necesario, no si mejoró la señal."
    )
    ping_pongs: int = Field(description="Handovers que formaron parte de un patrón A -> B -> A")
    tasa_hopp: float = Field(description="ping_pongs / total_handovers (%)")


class HourlyDistributionResponse(BaseModel):
    """Un elemento de la respuesta de GET /kpis/hourly: desglose de los
    handovers de una hora del día (0-23) por categoría."""

    hora: int = Field(description="Hora del día (0-23)")
    total: int = Field(description="Total de handovers detectados en esa hora")
    exitosos: int
    fallidos: int
    indeterminados: int
    ping_pongs: int


class FranjaHorariaResponse(BaseModel):
    """Un elemento de la respuesta de GET /kpis/franja-horaria: igual que
    HourlyDistributionResponse pero agrupado en 3 franjas en vez de 24 horas."""

    franja: str = Field(description="'manana' (06-11:59), 'tarde' (12-18:59) o 'noche' (19-05:59)")
    total: int
    exitosos: int
    fallidos: int
    indeterminados: int
    ping_pongs: int


class DiaSemanaResponse(BaseModel):
    """Un elemento de la respuesta de GET /kpis/dia-semana: desglose de los
    handovers de un día de la semana (Lunes a Domingo) por categoría."""

    dia: int = Field(description="Día de la semana: 0=Lunes ... 6=Domingo")
    etiqueta: str = Field(description="Nombre del día en español, ej. 'Lunes'")
    total: int
    exitosos: int
    fallidos: int
    indeterminados: int
    ping_pongs: int


class TrendResponse(BaseModel):
    """Un elemento de la respuesta de GET /kpis/trend: evolución de los KPIs
    agrupada por periodo (diario/semanal/mensual/anual)."""

    periodo: str = Field(description="Clave de agrupación técnica, ordenable (ej. '2026-05-06', '2026-W19')")
    etiqueta: str = Field(description="Etiqueta legible para el eje de la gráfica (ej. '06/05/26', 'Sem 19/2026')")
    total_handovers: int
    exitosos: int
    fallidos: int
    indeterminados: int
    ping_pongs: int
    tasa_exito: float = Field(description="exitosos / (exitosos + fallidos) (%) de ese periodo")
