"""
Servicios del módulo de KPIs: reglas de negocio sobre el dataset de
handovers (`handover_record`). No contiene SQLAlchemy ni ninguna sentencia
de acceso a datos — todo lo que necesita lo recibe de `KpisRepository`
(Repository Pattern, mismo patrón que usa `ingesta/services.py`).

Criterio de éxito de un handover ):
un handover es "exitoso" cuando TODOS los indicadores de señal disponibles
mejoran al pasar de la celda anterior a la nueva (RSSI, RSRQ y relación
señal/ruido -- rssnr). Si al menos uno de los disponibles empeora o se
mantiene igual, es "fallido" (equivalente a "handover innecesario": el
salto ocurrió pero no mejoró la conexión). Si ninguno de esos tres
indicadores está disponible en ambos lados de la transición (por ejemplo,
handovers de origen xlsx, que solo traen RSRP), se usa RSRP como respaldo;
si tampoco hay RSRP, el evento queda "indeterminado" -- cuenta para el
total de handovers pero no se puede clasificar como éxito o fallo.
"""

from datetime import date
from typing import Callable

from app.modules.kpis.repository import KpisRepository
from app.modules.kpis.schemas import (
    FranjaHorariaResponse,
    HourlyDistributionResponse,
    KpiSummaryResponse,
    SignalMetricsResponse,
    TrendResponse,
)

EXITOSO = "exitoso"
FALLIDO = "fallido"
INDETERMINADO = "indeterminado"

# Traduce la clasificación de un evento al nombre del campo donde se cuenta
# dentro de cada bucket de agregación (hora/franja/periodo).
CLASIFICACION_A_CAMPO = {
    EXITOSO: "exitosos",
    FALLIDO: "fallidos",
    INDETERMINADO: "indeterminados",
}

PERIODOS_VALIDOS = ("diario", "semanal", "mensual", "anual")
FRANJAS_VALIDAS = ("manana", "tarde", "noche")

_CONTADOR_VACIO = {"total": 0, "exitosos": 0, "fallidos": 0, "indeterminados": 0, "ping_pongs": 0}


def calcular_metricas_globales_dia(fecha: date, repositorio: KpisRepository) -> SignalMetricsResponse:
    """Calidad de señal general de un día puntual (no es específico de
    handovers, es una vista de todas las mediciones de ese día). Usado por
    GET /kpis/daily.
    """
    metricas = repositorio.obtener_metricas_diarias_senal(fecha)

    total = metricas["total"]
    criticos = metricas["criticos"]
    tasa_riesgo = (criticos / total * 100) if total > 0 else 0.0

    return SignalMetricsResponse(
        fecha=fecha,
        total_mediciones=total,
        promedio_rsrp=round(metricas["promedio"], 2),
        eventos_criticos=criticos,
        tasa_riesgo=round(tasa_riesgo, 2),
    )


def _clasificar_handover(registro_anterior: tuple, registro_actual: tuple) -> str:
    """Compara los indicadores de señal disponibles a ambos lados de una
    transición de celda y decide si el handover fue exitoso, fallido o
    indeterminado (ver criterio completo en el docstring del módulo).

    Cada tupla tiene el formato que devuelve
    `KpisRepository.obtener_secuencia_completa`:
    (cell_id, timestamp_medicion, rsrp_dbm, rssi, rsrq, rssnr).

    "Mejorar" significa que el valor de llegada es mayor (menos negativo)
    que el de salida -- válido tanto para RSSI/RSRQ/RSSNR como para RSRP,
    todos expresados en dBm/dB donde menos negativo es señal más fuerte.
    """
    _, _, _, rssi_anterior, rsrq_anterior, rssnr_anterior = registro_anterior
    _, _, _, rssi_actual, rsrq_actual, rssnr_actual = registro_actual

    pares_rf = [
        (rssi_anterior, rssi_actual),
        (rsrq_anterior, rsrq_actual),
        (rssnr_anterior, rssnr_actual),
    ]
    disponibles = [(anterior, actual) for anterior, actual in pares_rf if anterior is not None and actual is not None]

    if not disponibles:
        # Respaldo para transiciones de origen xlsx, que nunca traen
        # rssi/rsrq/rssnr (solo existen en registros de origen csv).
        rsrp_anterior, rsrp_actual = registro_anterior[2], registro_actual[2]
        if rsrp_anterior is not None and rsrp_actual is not None:
            disponibles = [(rsrp_anterior, rsrp_actual)]

    if not disponibles:
        return INDETERMINADO

    mejoro_en_todos_los_disponibles = all(actual > anterior for anterior, actual in disponibles)
    return EXITOSO if mejoro_en_todos_los_disponibles else FALLIDO


def _detectar_eventos_handover(secuencia: list[tuple]) -> list[dict]:
    """Recorre la secuencia cronológica de mediciones y arma la lista de
    eventos de handover: cada transición de celda es un evento, con su
    clasificación (éxito/fallo/indeterminado) y si formó parte de un patrón
    de ping-pong.

    Punto único de detección: `calcular_resumen_kpis`,
    `calcular_distribucion_horaria`, `calcular_distribucion_franja_horaria`
    y `calcular_tendencia` reutilizan esta lista en vez de cada uno volver a
    recorrer la secuencia cruda con su propia copia de esta lógica.
    """
    eventos: list[dict] = []
    if not secuencia:
        return eventos

    celda_actual = secuencia[0][0]
    celdas_visitadas = [celda_actual]

    for indice in range(1, len(secuencia)):
        registro_actual = secuencia[indice]
        celda_nueva = registro_actual[0]

        if celda_nueva == celda_actual:
            continue

        celdas_visitadas.append(celda_nueva)
        eventos.append(
            {
                "timestamp": registro_actual[1],
                "celda": celda_nueva,
                "clasificacion": _clasificar_handover(secuencia[indice - 1], registro_actual),
                "ping_pong": False,  # se completa en la pasada de abajo
            }
        )
        celda_actual = celda_nueva

    # Ping-pong = patrón A -> B -> A sobre las CELDAS VISITADAS (no sobre la
    # secuencia cruda de mediciones). celdas_visitadas[0] es la celda de
    # partida (no es un evento), así que celdas_visitadas[k] corresponde a
    # eventos[k-1].
    for indice in range(2, len(celdas_visitadas)):
        if celdas_visitadas[indice] == celdas_visitadas[indice - 2]:
            eventos[indice - 1]["ping_pong"] = True

    return eventos


def _agrupar_eventos(eventos: list[dict], funcion_clave: Callable[[dict], str]) -> dict[str, dict]:
    """Agrupa eventos de handover según `funcion_clave(evento) -> str` y
    acumula los conteos por categoría dentro de cada grupo. Reutilizado por
    distribución horaria, franja horaria y tendencia por periodo -- lo único
    que cambia entre esas tres es cómo se agrupa, no cómo se cuenta.
    """
    grupos: dict[str, dict] = {}
    for evento in eventos:
        clave = funcion_clave(evento)
        bucket = grupos.setdefault(clave, dict(_CONTADOR_VACIO))
        bucket["total"] += 1
        bucket[CLASIFICACION_A_CAMPO[evento["clasificacion"]]] += 1
        if evento["ping_pong"]:
            bucket["ping_pongs"] += 1
    return grupos


def calcular_resumen_kpis(
    fecha_inicio: date,
    fecha_fin: date,
    repositorio: KpisRepository,
    tecnologia: int | None = None,
    franja: str | None = None,
) -> KpiSummaryResponse:
    """Resumen agregado de KPIs de handover para un rango de fechas.

    `tasa_handover` = total_ho / total_mediciones: qué tan seguido ocurre un
    handover respecto al total de mediciones tomadas (no es una tasa de
    éxito). `tasa_exito` = exitosos / (exitosos + fallidos): de los
    handovers que sí se pudieron clasificar, qué porcentaje mejoró la
    conexión. Los indeterminados quedan fuera de ese denominador a propósito
    -- no hay evidencia para contarlos ni como éxito ni como fallo, e
    incluirlos abajo distorsionaría el porcentaje.
    """
    secuencia = repositorio.obtener_secuencia_completa(fecha_inicio, fecha_fin, tecnologia)
    total_mediciones = repositorio.contar_mediciones(fecha_inicio, fecha_fin, tecnologia, franja)
    eventos = _filtrar_por_franja(_detectar_eventos_handover(secuencia), franja)


    total_ho = len(eventos)
    exitosos = sum(1 for evento in eventos if evento["clasificacion"] == EXITOSO)
    fallidos = sum(1 for evento in eventos if evento["clasificacion"] == FALLIDO)
    indeterminados = sum(1 for evento in eventos if evento["clasificacion"] == INDETERMINADO)
    ping_pongs = sum(1 for evento in eventos if evento["ping_pong"])

    tasa_handover = (total_ho / total_mediciones * 100) if total_mediciones > 0 else 0.0
    clasificados = exitosos + fallidos
    tasa_exito = (exitosos / clasificados * 100) if clasificados > 0 else 0.0
    tasa_hopp = (ping_pongs / total_ho * 100) if total_ho > 0 else 0.0
    # "Handover innecesario" es, por definición acordada, el mismo concepto
    # que "fallido": el salto ocurrió pero no mejoró la conexión.
    tasa_innecesarios = (fallidos / total_ho * 100) if total_ho > 0 else 0.0

    return KpiSummaryResponse(
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        total_mediciones=total_mediciones,
        total_handovers=total_ho,
        tasa_handover=round(tasa_handover, 2),
        exitosos=exitosos,
        fallidos=fallidos,
        indeterminados=indeterminados,
        tasa_exito=round(tasa_exito, 2),
        tasa_innecesarios=round(tasa_innecesarios, 2),
        ping_pongs=ping_pongs,
        tasa_hopp=round(tasa_hopp, 2),
    )


def calcular_distribucion_horaria(
    fecha_inicio: date,
    fecha_fin: date,
    repositorio: KpisRepository,
    tecnologia: int | None = None,
    franja: str | None = None,
) -> list[HourlyDistributionResponse]:
    """Distribución de eventos de handover por hora del día (0-23), con el
    desglose de las 4 categorías en cada hora -- no solo el total, para que
    el frontend pueda graficar exitosos/fallidos/ping-pong/indeterminados
    juntos en vez de un único valor agregado.
    """
    secuencia = repositorio.obtener_secuencia_completa(fecha_inicio, fecha_fin, tecnologia)
    eventos = _filtrar_por_franja(_detectar_eventos_handover(secuencia), franja)
    grupos = _agrupar_eventos(eventos, lambda evento: evento["timestamp"].hour)

    return [
        HourlyDistributionResponse(hora=hora, **grupos.get(hora, _CONTADOR_VACIO))
        for hora in range(24)
    ]


def _franja_horaria(hora: int) -> str:
    """Clasifica una hora del día (0-23) en mañana/tarde/noche.
    Rangos: mañana 06:00-11:59, tarde 12:00-18:59, noche 19:00-05:59.
    """
    if 6 <= hora <= 11:
        return "manana"
    if 12 <= hora <= 18:
        return "tarde"
    return "noche"

def _filtrar_por_franja(eventos: list[dict], franja: str | None) -> list[dict]:
    """Filtra una lista de eventos de handover ya detectados, quedándose
    solo con los que ocurrieron dentro de la franja horaria pedida.

    Se aplica DESPUÉS de `_detectar_eventos_handover`, nunca antes: filtrar
    la secuencia cruda de mediciones antes de detectar transiciones podría
    generar handovers falsos entre mediciones que en la realidad no eran
    consecutivas (con huecos de horas fuera de la franja de por medio).
    """
    if franja is None:
        return eventos
    return [evento for evento in eventos if _franja_horaria(evento["timestamp"].hour) == franja]




def calcular_distribucion_franja_horaria(
    fecha_inicio: date,
    fecha_fin: date,
    repositorio: KpisRepository,
    tecnologia: int | None = None,
) -> list[FranjaHorariaResponse]:
    """Igual que `calcular_distribucion_horaria`, pero agrupado en 3 franjas
    en vez de 24 horas individuales."""
    secuencia = repositorio.obtener_secuencia_completa(fecha_inicio, fecha_fin, tecnologia)
    eventos = _detectar_eventos_handover(secuencia)
    grupos = _agrupar_eventos(eventos, lambda evento: _franja_horaria(evento["timestamp"].hour))

    return [
        FranjaHorariaResponse(franja=franja, **grupos.get(franja, _CONTADOR_VACIO))
        for franja in FRANJAS_VALIDAS
    ]


def _clave_periodo(timestamp, periodo: str) -> str:
    """Clave de agrupación para `calcular_tendencia`, según la periodicidad
    elegida. La semana usa el calendario ISO (`isocalendar`) en vez de
    `strftime("%W")` porque el numerado %W de Python no es el estándar ISO
    y puede desalinear la primera/última semana del año.
    """
    if periodo == "diario":
        return timestamp.strftime("%Y-%m-%d")
    if periodo == "semanal":
        anio_iso, semana_iso, _ = timestamp.isocalendar()
        return f"{anio_iso}-W{semana_iso:02d}"
    if periodo == "mensual":
        return timestamp.strftime("%Y-%m")
    return timestamp.strftime("%Y")  # anual


def _etiqueta_periodo(clave: str, periodo: str) -> str:
    """Convierte la clave de agrupación (formato técnico, ordenable) a una
    etiqueta legible para mostrar en el eje de la gráfica."""
    if periodo == "diario":
        anio, mes, dia = clave.split("-")
        return f"{dia}/{mes}"
    if periodo == "semanal":
        anio, semana = clave.split("-W")
        return f"Sem {semana}/{anio}"
    if periodo == "mensual":
        anio, mes = clave.split("-")
        return f"{mes}/{anio}"
    return clave  # anual: la propia clave ya es el año


def calcular_tendencia(
    fecha_inicio: date,
    fecha_fin: date,
    repositorio: KpisRepository,
    periodo: str = "diario",
    tecnologia: int | None = None,
    franja: str | None = None,
) -> list[TrendResponse]:
    """Evolución de los KPIs de handover a lo largo del tiempo, agrupada por
    `periodo` (diario/semanal/mensual/anual -- ver `PERIODOS_VALIDOS`).
    """
    secuencia = repositorio.obtener_secuencia_completa(fecha_inicio, fecha_fin, tecnologia)
    eventos = _filtrar_por_franja(_detectar_eventos_handover(secuencia), franja)
    grupos = _agrupar_eventos(eventos, lambda evento: _clave_periodo(evento["timestamp"], periodo))

    resultado = []
    for clave in sorted(grupos):
        valores = grupos[clave]
        exitosos, fallidos = valores["exitosos"], valores["fallidos"]
        clasificados = exitosos + fallidos
        tasa_exito = (exitosos / clasificados * 100) if clasificados > 0 else 0.0

        resultado.append(
            TrendResponse(
                periodo=clave,
                etiqueta=_etiqueta_periodo(clave, periodo),
                total_handovers=valores["total"],
                exitosos=exitosos,
                fallidos=fallidos,
                indeterminados=valores["indeterminados"],
                ping_pongs=valores["ping_pongs"],
                tasa_exito=round(tasa_exito, 2),
            )
        )
    return resultado
