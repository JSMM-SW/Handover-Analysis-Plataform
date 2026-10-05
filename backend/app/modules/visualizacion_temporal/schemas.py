"""
Contratos Pydantic del Módulo 2 (entrada y salida de la API).

Esta capa no importa ninguna otra del módulo: solo describe formas de datos. Los objetos que
maneja el detector son `dataclass` puras (`detector.py`); aquí se definen sus equivalentes
serializables para el router.

Nota sobre los parámetros RF: los cinco (`rsrp_dbm`, `rsrq_db`, `rssnr_db`, `rscp_dbm`,
`rssi_dbm`) son opcionales y `None` significa **sin medida válida**. Nunca 0 ni el centinela
2147483647 de la aplicación de medición (decisión D-5).
"""

from datetime import datetime, time
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TipoEvento = Literal["intra_frecuencia", "inter_frecuencia", "inter_rat", "desconocido"]
Confianza = Literal["alta", "baja"]

#: Parámetros RF que el módulo conoce, en el orden en que se muestran en la interfaz.
PARAMETROS_RF: tuple[str, ...] = ("rsrp_dbm", "rsrq_db", "rssnr_db", "rscp_dbm", "rssi_dbm")

#: Etiqueta legible de cada parámetro para la interfaz.
ETIQUETAS_RF: dict[str, str] = {
    "rsrp_dbm": "RSRP (dBm)",
    "rsrq_db": "RSRQ (dB)",
    "rssnr_db": "RSSNR (dB)",
    "rscp_dbm": "RSCP (dBm)",
    "rssi_dbm": "RSSI (dBm)",
}


class ParametrosDeteccion(BaseModel):
    """Parámetros del algoritmo de detección (cuerpo opcional del endpoint de detección)."""

    model_config = ConfigDict(extra="forbid")

    muestras_confirmacion: int = Field(
        default=2,
        ge=1,
        le=50,
        description=(
            "Muestras consecutivas que debe persistir la nueva celda para aceptar el cambio. "
            "Análogo empírico del time-to-trigger de 3GPP."
        ),
    )
    ventana_ping_pong_s: float = Field(
        default=10.0,
        gt=0,
        le=600,
        description="Ventana dentro de la cual volver a la celda anterior se marca como ping-pong.",
    )
    max_gap_s: float = Field(
        default=30.0,
        gt=0,
        le=3600,
        description=(
            "Salto temporal por encima del cual un cambio de celda se atribuye a pérdida de "
            "captura y no se registra como handover."
        ),
    )
    recalcular: bool = Field(
        default=True,
        description="Si es cierto, borra los eventos previos de la sesión antes de insertar.",
    )


class CeldaResumen(BaseModel):
    """Identidad de una celda tal como se muestra en la tabla de eventos (HU-C2-009)."""

    clave: str = Field(description="Identidad canónica: 'LTE:<ECI>' o '<tech>:<lac_tac>:<cid>'.")
    cid: int | None = None
    node_id: int | None = None
    psc_pci: int | None = None
    arfcn: int | None = None
    tech: str | None = None


class EventoHandover(BaseModel):
    """Un evento de handover detectado (HU-C2-001, HU-C2-009)."""

    id_evento: str | None = None
    sesion_id: str
    sesion_nombre: str | None = None

    timestamp_evento: datetime
    report_index_evento: int | None = None

    celda_origen: CeldaResumen
    celda_destino: CeldaResumen

    medicion_previa_id: str
    medicion_posterior_id: str

    tipo_evento: TipoEvento
    ping_pong: bool = False
    tipo_tecnologia: str | None = None
    confianza: Confianza = "alta"
    data_state_evento: str | None = None

    delta_rsrp_db: float | None = None
    delta_rsrq_db: float | None = None
    delta_rssnr_db: float | None = None
    delta_rscp_db: float | None = None
    delta_rssi_db: float | None = None

    duracion_permanencia_s: float
    muestras_confirmacion: int


class CoberturaParametro(BaseModel):
    """Cuántas medidas válidas hay de un parámetro RF en la sesión.

    Es lo que permite a la interfaz mostrar "sin datos válidos" de forma explícita en lugar de
    pintar una serie vacía sin explicación (decisión D-5).
    """

    parametro: str
    etiqueta: str
    n_validos: int
    n_mediciones: int
    pct_validos: float
    disponible: bool = Field(
        description="Falso cuando no hay ni una sola medida válida del parámetro en la sesión."
    )


class DiagnosticoDeteccion(BaseModel):
    """Qué descartó el detector y por qué. Material para la memoria de la tesis."""

    mediciones_recibidas: int = 0
    mediciones_sin_identidad: int = 0
    tramos_no_confirmados: int = 0
    cambios_descartados_por_hueco: int = 0
    sesiones_analizadas: int = 0


class ResumenDeteccion(BaseModel):
    """Resultado de ejecutar la detección sobre una sesión (criterio 3 de HU-C2-001)."""

    sesion_id: str
    sesion_nombre: str | None = None

    total_handovers: int = Field(description="Número total de handovers detectados (CA3).")
    por_tipo: dict[str, int] = Field(
        default_factory=dict,
        description="Conteo por tipo_evento: intra_frecuencia, inter_frecuencia, inter_rat…",
    )
    por_tecnologia: dict[str, int] = Field(
        default_factory=dict,
        description="Conteo por transición de tecnología, p. ej. 'LTE' o 'LTE->WCDMA'.",
    )
    total_ping_pong: int = 0
    total_confianza_baja: int = 0

    radiobases_involucradas: int = 0
    ventana_inicio: datetime | None = None
    ventana_fin: datetime | None = None

    cobertura_parametros: list[CoberturaParametro] = Field(default_factory=list)
    diagnostico: DiagnosticoDeteccion = Field(default_factory=DiagnosticoDeteccion)

    parametros_usados: ParametrosDeteccion = Field(default_factory=ParametrosDeteccion)
    duracion_ms: int = 0


# ================================================================================================
# Fase 3 — contratos de la API REST
# ================================================================================================


class ParametroRF(str, Enum):
    """Parámetros de radiofrecuencia que el módulo sabe representar.

    RSSNR figura aquí aunque el terminal del dataset de referencia nunca lo entregue: otros
    terminales sí lo miden y el módulo debe admitirlos sin rediseño (decisión D-5). Cuando no hay
    medida, la serie llega llena de `null` y `cobertura` lo declara explícitamente.
    """

    RSRP = "rsrp_dbm"
    RSRQ = "rsrq_db"
    RSSNR = "rssnr_db"
    RSCP = "rscp_dbm"
    RSSI = "rssi_dbm"


class Tecnologia(str, Enum):
    """Tecnología de acceso radio, tal como la reporta la aplicación de medición."""

    LTE = "LTE"
    WCDMA = "WCDMA"
    GSM = "GSM"


class EjeCelda(str, Enum):
    """Identificador con el que dibujar la secuencia de radiobases (HU-C2-003, decisión D-2)."""

    CELDA = "celda_clave"
    PCI = "psc_pci"


class IntervaloAnalisis(str, Enum):
    """Intervalo de agregación del histograma de radiobases repetidas (HU-C2-008)."""

    TOTAL = "total"
    HORA = "hora"
    DIEZ_MIN = "10min"
    CINCO_MIN = "5min"


class FiltrosTemporales(BaseModel):
    """Bloque de filtros común a los endpoints de lectura (HU-C2-006).

    Se analiza **una o varias sesiones** a la vez. `sesion_ids` es la lista completa; `sesion_id`
    se conserva como la primera de ellas para no romper a quien construye el filtro con una sola
    sesión. Al menos una es obligatoria: toda visualización es de recorridos concretos.
    """

    model_config = ConfigDict(extra="forbid")

    sesion_id: str | None = Field(
        default=None, description="Primera sesión analizada (compatibilidad con una sola sesión)."
    )
    sesion_ids: list[str] = Field(
        default_factory=list, description="Sesiones (recorridos) a analizar juntas."
    )
    desde: datetime | None = Field(default=None, description="Inicio del rango temporal.")
    hasta: datetime | None = Field(default=None, description="Fin del rango temporal.")
    hora_inicio: time | None = Field(
        default=None, description="Filtro de hora del día; se aplica a cada día del rango."
    )
    hora_fin: time | None = Field(default=None, description="Ídem.")
    tecnologia: list[Tecnologia] = Field(
        default_factory=list, description="Tecnologías a incluir. Vacío significa todas."
    )

    @model_validator(mode="after")
    def _validar_rangos(self) -> "FiltrosTemporales":
        # Une `sesion_id` y `sesion_ids` sin duplicados y conservando el orden de elección.
        sesiones = list(dict.fromkeys([*([self.sesion_id] if self.sesion_id else []), *self.sesion_ids]))
        sesiones = [s for s in sesiones if s]
        if not sesiones:
            raise ValueError("Hay que indicar al menos una sesión a analizar.")
        self.sesion_ids = sesiones
        self.sesion_id = sesiones[0]

        if self.desde and self.hasta and self.desde > self.hasta:
            raise ValueError("Rango inválido: 'desde' es posterior a 'hasta'.")
        if self.hora_inicio and self.hora_fin and self.hora_inicio >= self.hora_fin:
            raise ValueError("Rango horario inválido: 'hora_inicio' no es anterior a 'hora_fin'.")
        return self


class SesionOut(BaseModel):
    """Una sesión disponible para analizar."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sesion_id": "11111111-1111-4111-8111-111111111111",
                "sesion_nombre": "Session_S1_20260701_080000",
                "inicio": "2026-07-01T13:00:00Z",
                "fin": "2026-07-01T13:10:29Z",
                "n_mediciones": 600,
                "n_celdas": 8,
                "tecnologias": ["LTE", "WCDMA"],
                "origen": "sintetico",
                "n_handovers": 8,
            }
        }
    )

    sesion_id: str
    sesion_nombre: str | None = None
    inicio: datetime | None = None
    fin: datetime | None = None
    n_mediciones: int = 0
    n_celdas: int = 0
    tecnologias: list[str] = Field(default_factory=list)
    origen: str | None = Field(default=None, description="'real' o 'sintetico'.")
    n_handovers: int = 0


class PaginaHandovers(BaseModel):
    """Página de la tabla de eventos (HU-C2-009)."""

    total: int = 0
    page: int = 1
    page_size: int = 50
    items: list[EventoHandover] = Field(default_factory=list)


class SeriesOut(BaseModel):
    """Series temporales de parámetros RF, en formato columnar (HU-C2-004).

    Arrays paralelos a propósito: es lo que ECharts consume directamente y pesa mucho menos que
    una lista de objetos. Un `null` en `t` marca un **corte** de la línea por hueco de captura;
    un `null` dentro de una serie significa "sin medida válida en ese instante".
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "t": ["2026-07-01T13:00:00Z", "2026-07-01T13:00:01Z"],
                "series": {"rsrp_dbm": [-82, -83], "rssnr_db": [None, None]},
                "downsampled": False,
                "puntos_originales": 600,
                "puntos_devueltos": 600,
            }
        }
    )

    t: list[datetime | None] = Field(default_factory=list)
    series: dict[str, list[float | None]] = Field(default_factory=dict)
    downsampled: bool = False
    puntos_originales: int = 0
    puntos_devueltos: int = 0
    cobertura: list[CoberturaParametro] = Field(
        default_factory=list,
        description="Cobertura real de cada parámetro pedido, para avisar de 'sin datos válidos'.",
    )


class TramoCelda(BaseModel):
    """Permanencia continua en una celda, para la gráfica escalonada de HU-C2-003."""

    inicio: datetime
    fin: datetime
    celda_clave: str
    etiqueta: str = Field(description="Valor mostrado en el eje según el identificador elegido.")
    cid: int | None = None
    node_id: int | None = None
    psc_pci: int | None = None
    tech: str | None = None
    arfcn: int | None = None
    n_mediciones: int = 0
    duracion_s: float = 0.0
    valor_normalizado: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Altura estable de la celda en el eje Y. Se asigna por orden de primera aparición, "
            "de modo que una celda quede siempre a la misma altura aunque cambien los filtros."
        ),
    )


class TramosCeldaOut(BaseModel):
    """Secuencia temporal de celdas servidoras (HU-C2-003)."""

    eje: EjeCelda = EjeCelda.CELDA
    tramos: list[TramoCelda] = Field(default_factory=list)
    celdas_distintas: int = 0


class EstadisticasParametro(BaseModel):
    """Comparación pre/post de un parámetro alrededor de un handover (HU-C2-005)."""

    media_pre: float | None = None
    media_post: float | None = None
    delta: float | None = None
    n_pre: int = 0
    n_post: int = 0
    disponible: bool = True


class VentanaHandoverOut(BaseModel):
    """Ventana PRE / EVENTO / POST alrededor de un handover (HU-C2-005)."""

    evento: EventoHandover
    t_evento: datetime
    segundos_antes: float
    segundos_despues: float

    t: list[datetime] = Field(default_factory=list)
    t_relativo_s: list[float] = Field(default_factory=list)
    fase: list[str] = Field(default_factory=list, description="'pre', 'evento' o 'post'.")
    series: dict[str, list[float | None]] = Field(default_factory=dict)
    estadisticas: dict[str, EstadisticasParametro] = Field(default_factory=dict)


class ResumenOut(BaseModel):
    """Resumen general del dataset analizado (HU-C2-007)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_handovers": 8,
                "radiobases_involucradas": 8,
                "sesiones_analizadas": 1,
                "por_tipo": {"intra_frecuencia": 4, "inter_frecuencia": 2, "inter_rat": 2},
                "tasa_ho_por_minuto": 0.8,
            }
        }
    )

    total_handovers: int = 0
    radiobases_involucradas: int = 0
    sesiones_analizadas: int = 0
    n_mediciones: int = 0

    ventana_inicio: datetime | None = None
    ventana_fin: datetime | None = None
    duracion_s: float | None = None

    por_tipo: dict[str, int] = Field(default_factory=dict)
    por_tecnologia: dict[str, int] = Field(default_factory=dict)
    total_ping_pong: int = 0
    total_confianza_baja: int = 0
    tasa_ho_por_minuto: float | None = None

    cobertura_parametros: list[CoberturaParametro] = Field(default_factory=list)


class CeldaRepetida(BaseModel):
    """Una celda y cuántas veces se ha vuelto a ella (HU-C2-008)."""

    celda_clave: str
    cid: int | None = None
    node_id: int | None = None
    psc_pci: int | None = None
    tech: str | None = None
    n_visitas: int = Field(description="Tramos distintos en los que esta celda fue la servidora.")
    n_mediciones: int = 0
    tiempo_total_s: float = 0.0


class BinIntervalo(BaseModel):
    """Celdas repetidas dentro de un intervalo de análisis."""

    inicio: datetime | None = None
    fin: datetime | None = None
    celdas: list[CeldaRepetida] = Field(default_factory=list)


class CeldasRepetidasOut(BaseModel):
    """Distribución de radiobases repetidas (HU-C2-008)."""

    intervalo: IntervaloAnalisis = IntervaloAnalisis.TOTAL
    top: int = 20
    bins: list[BinIntervalo] = Field(default_factory=list)
    total_celdas: int = 0
