"""
Contratos Pydantic del Módulo 2 (entrada y salida de la API).

Esta capa no importa ninguna otra del módulo: solo describe formas de datos. Los objetos que
maneja el detector son `dataclass` puras (`detector.py`); aquí se definen sus equivalentes
serializables para el router.

Nota sobre los parámetros RF: los cinco (`rsrp_dbm`, `rsrq_db`, `rssnr_db`, `rscp_dbm`,
`rssi_dbm`) son opcionales y `None` significa **sin medida válida**. Nunca 0 ni el centinela
2147483647 de la aplicación de medición (decisión D-5).
"""

import re
from datetime import date, datetime, time
from enum import Enum
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


#: Forma admitida para una tecnología. Los valores **no se fijan en el código**: la interfaz
#: ofrece los que hay en la base (`GET /disponibilidad`), y uno que no aparezca en los datos
#: simplemente no deja pasar ninguna fila. El patrón solo descarta entradas sin sentido.
_PATRON_TECNOLOGIA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_+\-]{0,19}$")


def zona_horaria_valida(nombre: str) -> bool:
    """Indica si `nombre` es una zona IANA conocida (p. ej. 'America/Guayaquil')."""
    try:
        ZoneInfo(nombre)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


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
    tecnologia: list[str] = Field(
        default_factory=list, description="Tecnologías a incluir. Vacío significa todas."
    )
    zona_horaria: str = Field(
        default="UTC",
        description=(
            "Zona IANA en la que el usuario escribe la franja horaria. La base guarda los "
            "instantes en UTC; sin la zona, las 16:00 de Ecuador se compararían con las 16:00 UTC."
        ),
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

        invalidas = [t for t in self.tecnologia if not _PATRON_TECNOLOGIA.match(str(t))]
        if invalidas:
            raise ValueError(f"Tecnología no válida: {', '.join(map(str, invalidas))}.")
        if not zona_horaria_valida(self.zona_horaria):
            raise ValueError(f"Zona horaria desconocida: '{self.zona_horaria}'.")
        return self


class SesionOut(BaseModel):
    """Una sesión disponible para analizar."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sesion_id": "46bd7c25-3a0a-4ff0-b301-1221d5adb1c6",
                "sesion_nombre": "Sesión 134 · Session_32_20260928_162453.csv",
                "inicio": "2026-09-28T21:24:53Z",
                "fin": "2026-09-28T21:45:43Z",
                "n_mediciones": 1217,
                "n_celdas": 24,
                "tecnologias": ["LTE"],
                "n_handovers": 39,
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
    etiqueta: str = Field(
        description=(
            "Valor mostrado en el eje: la clave de la celda, o «PCI n» / «PSC n» / «<tech> CID n» "
            "con `eje=psc_pci`."
        )
    )
    sesion_id: str | None = Field(default=None, description="Sesión a la que pertenece el tramo.")
    sesion_nombre: str | None = None
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
            "Altura estable en el eje Y, una por rótulo (`etiqueta`): por celda con "
            "`eje=celda_clave` y por PCI/PSC con `eje=psc_pci`. Se asigna por orden de primera "
            "aparición, de modo que un rótulo quede siempre a la misma altura aunque cambien los "
            "filtros."
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

    celda_clave: str = Field(
        description="Celda; con `eje=psc_pci`, la primera de las que comparten el PCI/PSC."
    )
    etiqueta: str = Field(
        default="",
        description="Rótulo físico: «PCI n» (LTE), «PSC n» (WCDMA), «GSM CID n», «Sin PCI» o «Sin PSC».",
    )
    cid: int | None = None
    node_id: int | None = None
    psc_pci: int | None = None
    tech: str | None = None
    arfcn: int | None = Field(default=None, description="Canal de la primera celda.")
    celdas_incluidas: list[str] = Field(
        default_factory=list,
        description="Celdas que suman en esta barra (varias si comparten PCI/PSC).",
    )
    canales: list[int] = Field(default_factory=list, description="Canales de esas celdas.")
    n_visitas: int = Field(
        description=(
            "Veces que el terminal volvió: tramos de la celda, o rachas seguidas del mismo "
            "PCI/PSC con `eje=psc_pci`."
        )
    )
    n_mediciones: int = 0
    tiempo_total_s: float = 0.0


class BinIntervalo(BaseModel):
    """Celdas repetidas dentro de un intervalo de análisis."""

    inicio: datetime | None = None
    fin: datetime | None = None
    sesion_id: str | None = Field(
        default=None,
        description="Sesión a la que pertenece el intervalo. Nulo en el total, que las junta todas.",
    )
    sesion_nombre: str | None = None
    celdas: list[CeldaRepetida] = Field(default_factory=list)


class CeldasRepetidasOut(BaseModel):
    """Distribución de radiobases repetidas (HU-C2-008)."""

    intervalo: IntervaloAnalisis = IntervaloAnalisis.TOTAL
    minutos: int | None = Field(
        default=None,
        description="Duración de cada intervalo en minutos. Nulo cuando se analiza el total.",
    )
    minutos_max: int = Field(
        default=0,
        description=(
            "Minutos que dura la sesión más larga del rango filtrado: el tope útil del "
            "deslizador de intervalo, por encima del cual cada sesión cabe en un solo intervalo."
        ),
    )
    top: int = 20
    eje: EjeCelda = EjeCelda.CELDA
    bins: list[BinIntervalo] = Field(default_factory=list)
    total_celdas: int = Field(
        default=0, description="Barras distintas en todo el rango: celdas, o PCI/PSC con `eje=psc_pci`."
    )


# ================================================================================================
# Disponibilidad de datos — calendario y filtros de la configuración del análisis
# ================================================================================================


class FranjaHoraria(BaseModel):
    """Tramo continuo del día con mediciones, en la hora local del usuario."""

    inicio: time = Field(description="Primer minuto con mediciones (HH:MM).")
    fin: time = Field(description="Último minuto con mediciones, incluido (HH:MM).")


class DiaDisponible(BaseModel):
    """Un día con datos de las sesiones elegidas."""

    fecha: date = Field(description="Día en la zona horaria pedida.")
    n_mediciones: int = 0
    n_handovers: int = 0
    franjas: list[FranjaHoraria] = Field(default_factory=list)


class DisponibilidadOut(BaseModel):
    """Qué fechas, horas y tecnologías tienen datos en las sesiones elegidas.

    Alimenta el calendario y los filtros de la configuración del análisis: solo se ofrece lo que
    existe en la base, para que el usuario no tenga que ir probando día por día.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "zona_horaria": "America/Guayaquil",
                "dias": [
                    {
                        "fecha": "2026-09-28",
                        "n_mediciones": 1217,
                        "n_handovers": 39,
                        "franjas": [{"inicio": "16:24:00", "fin": "16:45:00"}],
                    }
                ],
                "tecnologias": ["LTE"],
            }
        }
    )

    zona_horaria: str
    dias: list[DiaDisponible] = Field(default_factory=list)
    tecnologias: list[str] = Field(default_factory=list)
