"""
Router del Módulo 2 — el puente HTTP.

Responsabilidad única: recibir peticiones, construir los filtros, delegar en `services` y traducir
las excepciones de dominio a códigos HTTP. **No contiene lógica de dominio ni SQL**
(`docs/02-arquitectura.md`).

Prefijo resultante: `/api/v1/visualizacion-temporal/...`
El `/api/v1` lo aplica `main.py`, siguiendo el patrón que ya usa el módulo de ingesta.
"""

import logging
from datetime import datetime, time

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.modules.visualizacion_temporal import services
from app.modules.visualizacion_temporal.exceptions import (
    HandoverNoEncontrado,
    SesionNoEncontrada,
    SesionSinMediciones,
)
from app.modules.visualizacion_temporal.repository import VisualizacionTemporalRepository
from app.modules.visualizacion_temporal.schemas import (
    CeldasRepetidasOut,
    EjeCelda,
    FiltrosTemporales,
    IntervaloAnalisis,
    PaginaHandovers,
    ParametroRF,
    ParametrosDeteccion,
    ResumenDeteccion,
    ResumenOut,
    SeriesOut,
    SesionOut,
    Tecnologia,
    TramosCeldaOut,
    VentanaHandoverOut,
)
from app.shared.db.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/visualizacion-temporal",
    tags=["Visualización Temporal"],
)


def obtener_repositorio(db: Session = Depends(get_db)) -> VisualizacionTemporalRepository:
    return VisualizacionTemporalRepository(db)


def filtros_comunes(
    sesion_id: list[str] = Query(
        description=(
            "Sesión o sesiones (recorridos) a analizar. Se repite el parámetro para analizar "
            "varias juntas: `?sesion_id=a&sesion_id=b`."
        ),
    ),
    desde: datetime | None = Query(default=None, description="Inicio del rango temporal."),
    hasta: datetime | None = Query(default=None, description="Fin del rango temporal."),
    hora_inicio: time | None = Query(
        default=None, description="Filtro de hora del día (HH:MM), aplicado a cada día del rango."
    ),
    hora_fin: time | None = Query(default=None, description="Ídem."),
    tecnologia: list[Tecnologia] = Query(
        default=[], description="Tecnologías a incluir. Vacío significa todas."
    ),
) -> FiltrosTemporales:
    """Bloque de filtros común a todos los endpoints de lectura (HU-C2-006).

    Las validaciones de coherencia (rango invertido, horario invertido) viven en el schema, y su
    `ValueError` se traduce aquí a un 422 con el detalle en español.
    """
    try:
        return FiltrosTemporales(
            sesion_ids=sesion_id,
            desde=desde,
            hasta=hasta,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            tecnologia=tecnologia,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


def _traducir(exc: Exception) -> HTTPException:
    """Traduce una excepción de dominio al código HTTP que le corresponde."""
    if isinstance(exc, (SesionNoEncontrada, HandoverNoEncontrado)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, SesionSinMediciones):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del módulo."
    )


# ================================================================================================
# 1. Sesiones disponibles
# ================================================================================================


@router.get(
    "/sesiones",
    response_model=list[SesionOut],
    summary="Listar las sesiones disponibles",
    description=(
        "Devuelve los recorridos que se pueden analizar, con su ventana temporal, número de "
        "mediciones, celdas distintas y handovers ya detectados. Alimenta el selector del header "
        "(HU-C2-006).\n\n"
        "El Módulo 1 no expone ningún listado de ejecuciones, así que el Módulo 2 lo construye "
        "a partir de las mediciones que lee."
    ),
)
def listar_sesiones(
    repositorio: VisualizacionTemporalRepository = Depends(obtener_repositorio),
) -> list[SesionOut]:
    return services.listar_sesiones(repositorio)


# ================================================================================================
# 2. Detección de handovers — HU-C2-001
# ================================================================================================


@router.post(
    "/sesiones/{sesion_id}/detectar-handovers",
    response_model=ResumenDeteccion,
    summary="Ejecutar la detección de handovers sobre una sesión",
    description=(
        "Recorre las mediciones de la sesión, identifica los cambios de celda servidora y "
        "persiste los eventos (HU-C2-001).\n\n"
        "Es **idempotente**: con `recalcular=true` (por defecto) borra los eventos previos de la "
        "sesión antes de insertar, de modo que reejecutarla con otros parámetros deja un estado "
        "limpio en lugar de acumular duplicados."
    ),
    responses={
        404: {"description": "La sesión no existe."},
        422: {"description": "La sesión no tiene mediciones con celda identificable."},
    },
)
def detectar_handovers(
    sesion_id: str = Path(description="Sesión sobre la que ejecutar la detección."),
    parametros: ParametrosDeteccion = ParametrosDeteccion(),
    repositorio: VisualizacionTemporalRepository = Depends(obtener_repositorio),
) -> ResumenDeteccion:
    try:
        return services.ejecutar_deteccion(sesion_id, parametros, repositorio)
    except (SesionNoEncontrada, SesionSinMediciones) as exc:
        raise _traducir(exc) from exc


# ================================================================================================
# 3. Tabla de eventos — HU-C2-009
# ================================================================================================


@router.get(
    "/handovers",
    response_model=PaginaHandovers,
    summary="Listar los handovers detectados",
    description=(
        "Página de eventos para la tabla de HU-C2-009, con celda origen y destino, tipo, "
        "confianza y los deltas de cada parámetro RF.\n\n"
        "Una sesión válida sin eventos devuelve 200 con la lista vacía: no es un error."
    ),
    responses={404: {"description": "La sesión no existe."}},
)
def listar_handovers(
    filtros: FiltrosTemporales = Depends(filtros_comunes),
    page: int = Query(default=1, ge=1, description="Página, empezando en 1."),
    page_size: int = Query(default=50, ge=1, le=500, description="Eventos por página."),
    orden: str = Query(default="asc", pattern="^(asc|desc)$", description="Orden temporal."),
    repositorio: VisualizacionTemporalRepository = Depends(obtener_repositorio),
) -> PaginaHandovers:
    try:
        return services.listar_handovers(filtros, page, page_size, orden, repositorio)
    except SesionNoEncontrada as exc:
        raise _traducir(exc) from exc


# ================================================================================================
# 4. Series de parámetros RF — HU-C2-004
# ================================================================================================


@router.get(
    "/series",
    response_model=SeriesOut,
    summary="Series temporales de parámetros de radiofrecuencia",
    description=(
        "Devuelve las series en **formato columnar** (arrays paralelos): es lo que ECharts "
        "consume directamente y pesa mucho menos que una lista de objetos.\n\n"
        "- Un `null` en `t` marca un **corte** de la línea por hueco de captura.\n"
        "- Un `null` dentro de una serie significa **sin medida válida** en ese instante.\n"
        "- Si la serie excede `max_puntos` se aplica downsampling **LTTB**, que conserva picos y "
        "valles; `downsampled` y `puntos_originales` lo declaran.\n"
        "- `cobertura` informa de cuántas medidas válidas tiene cada parámetro, para poder "
        "mostrar *sin datos válidos* en lugar de una gráfica vacía sin explicación."
    ),
    responses={404: {"description": "La sesión no existe."}},
)
def obtener_series(
    filtros: FiltrosTemporales = Depends(filtros_comunes),
    parametros: list[ParametroRF] = Query(
        default=[], description="Parámetros a devolver. Vacío significa todos."
    ),
    max_puntos: int = Query(
        default=3000, ge=10, le=50000, description="Máximo de puntos por serie."
    ),
    max_gap_s: float = Query(
        default=services.MAX_GAP_GRAFICA_S,
        gt=0,
        description="Salto temporal por encima del cual la línea se corta.",
    ),
    repositorio: VisualizacionTemporalRepository = Depends(obtener_repositorio),
) -> SeriesOut:
    try:
        return services.obtener_series(
            filtros,
            parametros=parametros,
            max_puntos=max_puntos,
            max_gap_s=max_gap_s,
            repository=repositorio,
        )
    except SesionNoEncontrada as exc:
        raise _traducir(exc) from exc


# ================================================================================================
# 5. Secuencia de radiobases — HU-C2-003
# ================================================================================================


@router.get(
    "/series-celdas",
    response_model=TramosCeldaOut,
    summary="Secuencia temporal de la celda servidora",
    description=(
        "Tramos de permanencia en cada celda, para la gráfica escalonada de HU-C2-003.\n\n"
        "`eje` permite elegir el identificador: `celda_clave` (ECI, por defecto) o `psc_pci`. "
        "El ECI es el recomendado porque es único dentro del operador, mientras que el PCI se "
        "reutiliza entre emplazamientos y además falta en la mayoría de las filas reales.\n\n"
        "`valor_normalizado` se asigna por orden de primera aparición, de modo que una celda "
        "ocupe siempre la misma altura aunque cambien los filtros."
    ),
    responses={404: {"description": "La sesión no existe."}},
)
def obtener_series_celdas(
    filtros: FiltrosTemporales = Depends(filtros_comunes),
    eje: EjeCelda = Query(default=EjeCelda.CELDA, description="Identificador del eje Y."),
    repositorio: VisualizacionTemporalRepository = Depends(obtener_repositorio),
) -> TramosCeldaOut:
    try:
        return services.obtener_tramos_celda(filtros, eje=eje, repository=repositorio)
    except SesionNoEncontrada as exc:
        raise _traducir(exc) from exc


# ================================================================================================
# 6. Ventana PRE/POST de un handover — HU-C2-005
# ================================================================================================


@router.get(
    "/handovers/{id_evento}/ventana",
    response_model=VentanaHandoverOut,
    summary="Ventana antes/durante/después de un handover",
    description=(
        "Recorta la ventana configurable alrededor del evento y devuelve, por parámetro, la "
        "serie, la fase de cada punto (`pre`, `evento`, `post`) y las estadísticas comparativas "
        "media_pre / media_post / delta (HU-C2-005).\n\n"
        "Con muestreo a 1 Hz, ±5 s son unos 11 puntos; la ventana se deja ampliable para "
        "capturas menos densas."
    ),
    responses={404: {"description": "El handover no existe."}},
)
def obtener_ventana_handover(
    id_evento: str = Path(description="Identificador del evento."),
    segundos_antes: float = Query(default=5.0, gt=0, le=3600, description="Ventana pre-HO."),
    segundos_despues: float = Query(default=5.0, gt=0, le=3600, description="Ventana post-HO."),
    parametros: list[ParametroRF] = Query(
        default=[], description="Parámetros a devolver. Vacío significa todos."
    ),
    repositorio: VisualizacionTemporalRepository = Depends(obtener_repositorio),
) -> VentanaHandoverOut:
    try:
        return services.obtener_ventana_handover(
            id_evento,
            segundos_antes=segundos_antes,
            segundos_despues=segundos_despues,
            parametros=parametros,
            repository=repositorio,
        )
    except HandoverNoEncontrado as exc:
        raise _traducir(exc) from exc


# ================================================================================================
# 7. Resumen — HU-C2-007
# ================================================================================================


@router.get(
    "/resumen",
    response_model=ResumenOut,
    summary="Resumen general del dataset analizado",
    description=(
        "Totales del recorrido: handovers, radiobases involucradas, sesiones analizadas, ventana "
        "temporal, desglose por tipo y por tecnología, y tasa de handovers por minuto "
        "(HU-C2-007).\n\n"
        "Incluye la cobertura de cada parámetro RF, que es lo que permite avisar de que un "
        "parámetro no tiene ninguna medida válida."
    ),
    responses={404: {"description": "La sesión no existe."}},
)
def obtener_resumen(
    filtros: FiltrosTemporales = Depends(filtros_comunes),
    repositorio: VisualizacionTemporalRepository = Depends(obtener_repositorio),
) -> ResumenOut:
    try:
        return services.obtener_resumen(filtros, repository=repositorio)
    except SesionNoEncontrada as exc:
        raise _traducir(exc) from exc


# ================================================================================================
# 8. Radiobases repetidas — HU-C2-008
# ================================================================================================


@router.get(
    "/celdas-repetidas",
    response_model=CeldasRepetidasOut,
    summary="Distribución de radiobases repetidas",
    description=(
        "Histograma de cuántas veces se ha vuelto a cada celda (HU-C2-008). Una *visita* es un "
        "tramo de permanencia: si el terminal regresa a la misma celda más tarde, cuenta otra "
        "vez, que es lo que revela los patrones de movilidad y las zonas de solapamiento.\n\n"
        "`intervalo` permite agrupar por hora, 10 o 5 minutos, además del total."
    ),
    responses={404: {"description": "La sesión no existe."}},
)
def obtener_celdas_repetidas(
    filtros: FiltrosTemporales = Depends(filtros_comunes),
    intervalo: IntervaloAnalisis = Query(
        default=IntervaloAnalisis.TOTAL, description="Intervalo de análisis."
    ),
    top: int = Query(default=20, ge=1, le=200, description="Celdas más frecuentes a devolver."),
    repositorio: VisualizacionTemporalRepository = Depends(obtener_repositorio),
) -> CeldasRepetidasOut:
    try:
        return services.obtener_celdas_repetidas(
            filtros, intervalo=intervalo, top=top, repository=repositorio
        )
    except SesionNoEncontrada as exc:
        raise _traducir(exc) from exc
