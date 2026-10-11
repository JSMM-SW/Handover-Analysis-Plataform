"""
Servicios del módulo de KPIs: reglas de negocio sobre el dataset de
handovers (`handover_record`). No contiene SQLAlchemy ni ninguna sentencia
de acceso a datos -- todo lo que necesita lo recibe de `KpisRepository`
(Repository Pattern, mismo patrón que usa `ingesta/services.py`).

Criterio de éxito/fallo de un handover -- PHD (Post Handover Degradado):
    PHD = (rssi_destino <= rssi_origen) OR (rsrq_destino < rsrq_origen)
Si PHD se cumple, el handover degradó la conexión -> "fallido". Si no se
cumple, la conexión mejoró o se mantuvo mejor -> "exitoso". Nótese la
asimetría intencional entre los dos operadores: en RSSI, quedarse igual ya
cuenta como degradación (<=); en RSRQ, quedarse igual NO cuenta como
degradación, solo empeorar sí (<, estricto). Reemplaza al criterio anterior
(RSSI+RSRQ+RSSNR con AND y respaldo de RSRP) -- decisión tomada con el
usuario: PHD es la fórmula de referencia, tener dos criterios de
éxito/fallo en paralelo sería confuso e indefendible en la tesis.

Solo se evalúa si RSSI y RSRQ están disponibles en AMBOS lados de la
transición. Si faltan, el handover queda "indeterminado": no hay respaldo
de RSRP definido para PHD, decisión explícita del usuario.

Criterio de UHO (Unnecessary Handover / Handover Innecesario):
    UHO = (rssi_origen >= -100 dBm) AND (rsrq_origen >= -15 dB)
Se evalúa solo con la medición de la celda de ORIGEN (antes del handover)
-- decisión explícita del usuario: el handover fue innecesario si, de
donde salió, la señal ya era suficientemente buena; no importa qué tan
buena o mala haya sido la señal en la celda de destino. Es independiente
de PHD: un mismo handover puede ser UHO y no estar degradado (PHD falso),
o no ser UHO y sí estar degradado -- no son mutuamente excluyentes,
responden preguntas distintas (¿hacía falta el salto? vs ¿el salto ayudó
o perjudicó?).

PHD y UHO solo entre mediciones LTE (Paso 5 del plan de refactor, oct
2026): ambas fórmulas comparan indicadores de señal (RSSI, RSRQ) que no
son comparables entre tecnologías distintas -- un RSSI de 3G no significa
lo mismo que uno de LTE. PHD exige que origen Y destino sean LTE; UHO
exige que el origen sea LTE. Si no, el handover queda "indeterminado"
(PHD) o "no evaluable" (UHO), con el mismo tratamiento que si faltara
RSSI/RSRQ. `total_handovers`/`tasa_handover` no se ven afectados -- todo
handover se sigue contando ahí, esta restricción es solo para PHD/UHO.


Agrupación por sesión y por tramos (Paso 2 del plan de refactor, oct 2026):
la secuencia que entrega el repositorio mezcla todas las sesiones y
tecnologías del rango de fechas. Un handover nunca se detecta entre
mediciones de sesiones distintas (cada sesión es una grabación
independiente), ni entre mediciones de la misma sesión separadas por un
hueco de datos mayor a HUECO_MAXIMO_SEGUNDOS -- en ese hueco pudo pasar
cualquier cosa (incluido un cambio de celda) sin quedar registrada. Ver
`_dividir_en_tramos`.

Ventana de ping-pong (Paso 3 del plan de refactor, oct 2026): un patrón
A -> B -> A solo cuenta como ping-pong si el regreso (B -> A) ocurre
dentro de PING_PONG_VENTANA_SEGUNDOS desde la ida (A -> B); un regreso más
tardío es un segundo cambio de celda independiente, no un rebote de señal.
Fuente: V. Parraga-Villamar, P. Lupera-Morillo y F. Grijalva, "How
efficient are handovers in mobile networks? A data-driven approach,"
Electronics, vol. 14, art. 3208, 2025.

Filtro de tecnología después de detectar (Paso 4 del plan de refactor, oct
2026): la secuencia que entrega el repositorio ya no se filtra por
tecnología en SQL -- se detecta sobre la secuencia COMPLETA de cada sesión
(todas las tecnologías mezcladas) y luego se conserva un handover solo si
la tecnología de origen Y la de destino están entre las seleccionadas. Ver
`_filtrar_por_tecnologia`. Mismo motivo que la franja horaria (Paso 1):
filtrar antes de detectar podría quitar una medición "puente" de otra
tecnología y unir dos mediciones que en la realidad no eran consecutivas,
generando un handover falso.
"""

import calendar
from datetime import date
from typing import Callable
from zoneinfo import ZoneInfo
from app.modules.kpis.repository import KpisRepository


from app.modules.kpis.schemas import (
    DiaSemanaResponse,
    FranjaHorariaResponse,
    HourlyDistributionResponse,
    KpiSummaryResponse,
    SesionResponse,
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

DIAS_SEMANA_ETIQUETAS = {
    0: "Lunes",
    1: "Martes",
    2: "Miércoles",
    3: "Jueves",
    4: "Viernes",
    5: "Sábado",
    6: "Domingo",
}
DIAS_SEMANA_ORDEN = tuple(range(7))  # 0=Lunes ... 6=Domingo, orden de datetime.weekday()


# Umbrales de la fórmula UHO (ver docstring del módulo). Confirmados por el
# usuario, no inventados -- no modificar sin volver a confirmar con él.
UHO_RSSI_MIN_DBM = -100
UHO_RSRQ_MIN_DB = -15

# Mismo mapeo que ingesta/etl/normalizer.py: 1=LTE/4G, 2=3G, 3=2G. PHD y
# UHO solo se evalúan entre mediciones LTE (ver docstring del módulo).
TECNOLOGIA_LTE = 1


# Mismo criterio que ingesta/etl/normalizer.py y kpis/repository.py: los
# timestamps llegan en UTC, hay que convertirlos antes de clasificar por
# hora/día/franja -- si no, todo queda desfasado 5 horas respecto a la
# hora real en Ecuador.
ZONA_HORARIA_ORIGEN = ZoneInfo("America/Guayaquil")

# Si entre dos mediciones consecutivas de la MISMA sesión pasan más de
# esto, se considera que hay un hueco de datos: la secuencia se corta en
# dos tramos y no se detecta handover entre ellos (ni se encadena un
# ping-pong a través del corte). Confirmado por el usuario.
HUECO_MAXIMO_SEGUNDOS = 10

# Ventana máxima entre la ida (A -> B) y el regreso (B -> A) para que un
# patrón A -> B -> A cuente como ping-pong (ver docstring del módulo y la
# cita bibliográfica). Un regreso más tardío es un segundo handover
# independiente, no un rebote de señal.
PING_PONG_VENTANA_SEGUNDOS = 60


_CONTADOR_VACIO = {
    "total": 0, "exitosos": 0, "fallidos": 0, "indeterminados": 0, "ping_pongs": 0,
    "uho_eventos": 0, "uho_evaluables": 0,
}



def calcular_metricas_globales_dia(fecha: date, repositorio: KpisRepository) -> SignalMetricsResponse:
    """Calidad de señal general de un día puntual (no es específico de
    handovers, es una vista de todas las mediciones de ese día). Usado por
    GET /kpis/daily.
    """
    metricas = repositorio.obtener_metricas_diarias_senal(fecha)

    total = metricas["total"]
    criticos = metricas["criticos"]
    total_rsrp = metricas.get("total_rsrp", total)
    tasa_riesgo = (criticos / total_rsrp * 100) if criticos is not None and total_rsrp > 0 else None

    return SignalMetricsResponse(
        fecha=fecha,
        total_mediciones=total,
        promedio_rsrp=round(metricas["promedio"], 2) if metricas["promedio"] is not None else None,
        eventos_criticos=criticos,
        tasa_riesgo=round(tasa_riesgo, 2) if tasa_riesgo is not None else None,
    )

def listar_sesiones(repositorio: KpisRepository) -> list[SesionResponse]:
    """Lista las sesiones (cargas de archivo) disponibles para poblar el
    selector de sesión del frontend, con el rango de fechas que cada una
    cubre (ver `KpisRepository.listar_sesiones`) -- así el frontend puede
    ajustar la ventana temporal automáticamente al elegir una sesión."""
    filas = repositorio.listar_sesiones()
    return [
        SesionResponse(
            sesion_label=ejecucion.sesion_label,
            filename=ejecucion.filename,
            processing_date=ejecucion.processing_date,
            records_valid=ejecucion.records_valid,
            primera_medicion=primera_medicion,
            ultima_medicion=ultima_medicion,
        )
        for ejecucion, primera_medicion, ultima_medicion in filas
    ]




def _clasificar_handover(registro_anterior: tuple, registro_actual: tuple) -> str:
    """Clasifica un handover como exitoso/fallido/indeterminado usando el
    criterio PHD (ver docstring del módulo para la fórmula completa).

    Cada tupla tiene el formato que devuelve
    `KpisRepository.obtener_secuencia_completa`:
    (cell_id, timestamp_medicion, rsrp_dbm, rssi, rsrq, rssnr,
    execution_id, tecnologia, report_index).
    `registro_anterior` = celda de ORIGEN, `registro_actual` = celda de
    DESTINO -- ese orden importa para la fórmula PHD (rssi_destino vs
    rssi_origen, no al revés).
    """
    _, _, _, rssi_origen, rsrq_origen, _, _, tecnologia_origen, _ = registro_anterior
    _, _, _, rssi_destino, rsrq_destino, _, _, tecnologia_destino, _ = registro_actual


    if tecnologia_origen != TECNOLOGIA_LTE or tecnologia_destino != TECNOLOGIA_LTE:
        return INDETERMINADO

    if rssi_origen is None or rssi_destino is None or rsrq_origen is None or rsrq_destino is None:
        return INDETERMINADO

    # PHD: rssi igual o peor (<=) YA cuenta como degradación; rsrq solo si
    # empeoró estrictamente (<) -- asimetría intencional de la fórmula.
    degradado = (rssi_destino <= rssi_origen) or (rsrq_destino < rsrq_origen)
    return FALLIDO if degradado else EXITOSO


def _es_uho(registro_origen: tuple) -> bool | None:
    """Evalúa la fórmula UHO (ver docstring del módulo) sobre la medición de
    la celda de ORIGEN de un handover -- antes de saltar, no importa a
    dónde saltó.

    Devuelve None si el origen no es LTE o si le falta RSSI/RSRQ: no se
    puede evaluar, no cuenta ni como UHO ni como "no UHO".
    """
    _, _, _, rssi_origen, rsrq_origen, _, _, tecnologia_origen, _ = registro_origen

    if tecnologia_origen != TECNOLOGIA_LTE:
        return None
    if rssi_origen is None or rsrq_origen is None:
        return None
    return rssi_origen >= UHO_RSSI_MIN_DBM and rsrq_origen >= UHO_RSRQ_MIN_DB



def _dividir_en_tramos(secuencia: list[tuple]) -> tuple[list[list[tuple]], int]:
    """Divide la secuencia (ya ordenada por sesión y tiempo, ver
    `KpisRepository.obtener_secuencia_completa`) en tramos contiguos:
    nunca se detecta un handover entre mediciones de sesiones distintas,
    ni entre mediciones de la misma sesión separadas por un hueco de más
    de HUECO_MAXIMO_SEGUNDOS -- en ese hueco pudo haber pasado cualquier
    cosa (incluido un cambio de celda) sin quedar registrada.

    Devuelve los tramos y, aparte, cuántos de los cortes POR HUECO (no
    los de cambio de sesión) tenían una celda distinta antes y después:
    son cambios de celda que probablemente ocurrieron pero no se pueden
    contar como handover porque no hay mediciones de por medio que lo
    confirmen.
    """
    if not secuencia:
        return [], 0

    tramos: list[list[tuple]] = [[secuencia[0]]]
    cambios_celda_no_observados = 0

    for anterior, actual in zip(secuencia, secuencia[1:]):
        misma_sesion = actual[6] == anterior[6]
        hueco_segundos = (actual[1] - anterior[1]).total_seconds() if misma_sesion else None

        corta = not misma_sesion or hueco_segundos > HUECO_MAXIMO_SEGUNDOS
        if corta:
            if misma_sesion and actual[0] != anterior[0]:
                cambios_celda_no_observados += 1
            tramos.append([])
        tramos[-1].append(actual)

    return tramos, cambios_celda_no_observados


def _detectar_eventos_en_tramo(tramo: list[tuple]) -> list[dict]:
    """Detecta los eventos de handover dentro de UN tramo (ver
    `_dividir_en_tramos`): mediciones consecutivas de la misma sesión, sin
    huecos de datos de por medio. El ping-pong (A -> B -> A) solo se
    encadena dentro del tramo -- nunca cruza un corte de sesión o de
    hueco, porque `celdas_visitadas` arranca de cero en cada tramo -- y
    solo si el regreso ocurre dentro de PING_PONG_VENTANA_SEGUNDOS desde
    la ida (ver docstring del módulo).
    """
    eventos: list[dict] = []
    if len(tramo) < 2:
        return eventos

    celda_actual = tramo[0][0]
    celdas_visitadas = [celda_actual]

    for indice in range(1, len(tramo)):
        registro_origen = tramo[indice - 1]
        registro_actual = tramo[indice]
        celda_nueva = registro_actual[0]

        if celda_nueva == celda_actual:
            continue

        celdas_visitadas.append(celda_nueva)
        eventos.append(
            {
                "timestamp": registro_actual[1].astimezone(ZONA_HORARIA_ORIGEN),
                "celda": celda_nueva,
                "clasificacion": _clasificar_handover(registro_origen, registro_actual),
                "uho": _es_uho(registro_origen),
                "tecnologia_origen": registro_origen[7],
                "tecnologia_destino": registro_actual[7],
                "ping_pong": False,  # se completa en la pasada de abajo
            }
        )

        celda_actual = celda_nueva

    # Ping-pong = patrón A -> B -> A sobre las CELDAS VISITADAS (no sobre la
    # secuencia cruda de mediciones), Y el regreso ocurre dentro de
    # PING_PONG_VENTANA_SEGUNDOS desde la ida. celdas_visitadas[0] es la
    # celda de partida (no es un evento), así que celdas_visitadas[k]
    # corresponde a eventos[k-1]: el evento de ida es eventos[indice-2], el
    # de regreso (el que se marca) es eventos[indice-1].
    for indice in range(2, len(celdas_visitadas)):
        if celdas_visitadas[indice] != celdas_visitadas[indice - 2]:
            continue
        evento_ida = eventos[indice - 2]
        evento_regreso = eventos[indice - 1]
        segundos_regreso = (evento_regreso["timestamp"] - evento_ida["timestamp"]).total_seconds()
        if segundos_regreso <= PING_PONG_VENTANA_SEGUNDOS:
            evento_regreso["ping_pong"] = True

    return eventos


def _detectar_eventos_handover(secuencia: list[tuple]) -> tuple[list[dict], int]:
    """Recorre la secuencia de mediciones y arma la lista de eventos de
    handover, agrupando primero por sesión y cortando en tramos donde haya
    un hueco de datos mayor a HUECO_MAXIMO_SEGUNDOS (ver
    `_dividir_en_tramos`).

    Devuelve `(eventos, cambios_celda_no_observados)`: el segundo valor
    cuenta los cortes por hueco (no los de cambio de sesión) donde la
    celda antes y después del hueco era distinta.

    Punto único de detección: `calcular_resumen_kpis`,
    `calcular_distribucion_horaria`, `calcular_distribucion_franja_horaria`,
    `calcular_distribucion_dia_semana` y `calcular_tendencia` reutilizan
    esta lista en vez de cada uno volver a recorrer la secuencia cruda con
    su propia copia de esta lógica.
    """
    tramos, cambios_celda_no_observados = _dividir_en_tramos(secuencia)

    eventos: list[dict] = []
    for tramo in tramos:
        eventos.extend(_detectar_eventos_en_tramo(tramo))

    return eventos, cambios_celda_no_observados


def _agrupar_eventos(eventos: list[dict], funcion_clave: Callable[[dict], str | int]) -> dict[str | int, dict]:
    """Agrupa eventos de handover según `funcion_clave(evento) -> str | int` y
    acumula los conteos por categoría dentro de cada grupo. Reutilizado por
    distribución horaria, franja horaria y tendencia por periodo -- lo único
    que cambia entre esas tres es cómo se agrupa, no cómo se cuenta.

    También acumula uho_eventos/uho_evaluables (Paso 9 del plan de
    refactor) -- solo los usa `calcular_tendencia`, los demás endpoints
    simplemente no los leen del bucket.
    """
    grupos: dict[str | int, dict] = {}
    for evento in eventos:
        clave = funcion_clave(evento)
        bucket = grupos.setdefault(clave, dict(_CONTADOR_VACIO))
        bucket["total"] += 1
        bucket[CLASIFICACION_A_CAMPO[evento["clasificacion"]]] += 1
        if evento["ping_pong"]:
            bucket["ping_pongs"] += 1
        if evento["uho"] is True:
            bucket["uho_eventos"] += 1
        if evento["uho"] is not None:
            bucket["uho_evaluables"] += 1
    return grupos




def _filtrar_por_tecnologia(eventos: list[dict], tecnologias: list[int] | None) -> list[dict]:
    """Filtra una lista de eventos de handover ya detectados, quedándose
    solo con los que tienen AMBOS extremos (tecnología de origen Y de
    destino) dentro de la selección pedida. Una lista vacía o None se
    trata como "todas" (sin filtro).

    Se aplica DESPUÉS de `_detectar_eventos_handover`, nunca antes: la
    secuencia que llega del repositorio ya no se filtra por tecnología en
    SQL (ver `KpisRepository.obtener_secuencia_completa`) -- filtrarla
    antes de detectar podría quitar una medición "puente" de otra
    tecnología y unir dos mediciones que en la realidad no eran
    consecutivas, generando un handover falso (mismo motivo que la franja
    horaria).
    """
    if not tecnologias:
        return eventos
    conjunto = set(tecnologias)
    return [
        evento for evento in eventos
        if evento["tecnologia_origen"] in conjunto and evento["tecnologia_destino"] in conjunto
    ]



def calcular_resumen_kpis(
    fecha_inicio: date,
    fecha_fin: date,
    repositorio: KpisRepository,
    tecnologia: list[int] | None = None,
    franja: list[str] | None = None,
    sesion_label: list[int] | None = None,
) -> KpiSummaryResponse:

    """Resumen agregado de KPIs de handover para un rango de fechas.

    `tasa_handover` = total_ho / total_mediciones: qué tan seguido ocurre un
    handover respecto al total de mediciones tomadas (no es una tasa de
    éxito). `tasa_exito` = exitosos / (exitosos + fallidos), `tasa_phd` es
    su complemento (fallidos / (exitosos + fallidos), mismo denominador),
    según el criterio PHD. `tasa_innecesarios` = uho_eventos /
    evaluables_uho, según el criterio UHO -- independiente de PHD (ver
    docstring del módulo). Los indeterminados (de PHD) y los
    no-evaluables-para-UHO quedan fuera de sus respectivos denominadores a
    propósito -- no hay evidencia para contarlos en ningún sentido, e
    incluirlos distorsionaría el porcentaje.

    Todas las tasas son `None` (Paso 6 del plan de refactor, oct 2026)
    cuando su denominador es 0 -- "sin datos", no un 0% real. El frontend
    debe mostrar "Sin datos" en vez de "0%" en ese caso.
    """
    secuencia = repositorio.obtener_secuencia_completa(fecha_inicio, fecha_fin, sesion_label)
    total_mediciones = repositorio.contar_mediciones(fecha_inicio, fecha_fin, tecnologia, franja, sesion_label)
    conjunto_tecnologia = set(tecnologia) if tecnologia else None
    celdas_distintas = len({
        registro[0] for registro in secuencia
        if conjunto_tecnologia is None or registro[7] in conjunto_tecnologia
    })
    eventos_detectados, cambios_celda_no_observados = _detectar_eventos_handover(secuencia)
    eventos = _filtrar_por_tecnologia(eventos_detectados, tecnologia)
    eventos = _filtrar_por_franja(eventos, franja)
    total_ho = len(eventos)

    exitosos = sum(1 for evento in eventos if evento["clasificacion"] == EXITOSO)
    fallidos = sum(1 for evento in eventos if evento["clasificacion"] == FALLIDO)
    indeterminados = sum(1 for evento in eventos if evento["clasificacion"] == INDETERMINADO)
    ping_pongs = sum(1 for evento in eventos if evento["ping_pong"])

    uho_eventos = sum(1 for evento in eventos if evento["uho"] is True)
    uho_evaluables = sum(1 for evento in eventos if evento["uho"] is not None)

    tasa_handover = (total_ho / total_mediciones * 100) if total_mediciones > 0 else None
    clasificados = exitosos + fallidos
    tasa_exito = (exitosos / clasificados * 100) if clasificados > 0 else None
    tasa_phd = (fallidos / clasificados * 100) if clasificados > 0 else None
    tasa_hopp = (ping_pongs / total_ho * 100) if total_ho > 0 else None
    tasa_innecesarios = (uho_eventos / uho_evaluables * 100) if uho_evaluables > 0 else None

    return KpiSummaryResponse(
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        total_mediciones=total_mediciones,
        total_handovers=total_ho,
        tasa_handover=round(tasa_handover, 2) if tasa_handover is not None else None,
        exitosos=exitosos,
        fallidos=fallidos,
        indeterminados=indeterminados,
        tasa_exito=round(tasa_exito, 2) if tasa_exito is not None else None,
        tasa_phd=round(tasa_phd, 2) if tasa_phd is not None else None,
        tasa_innecesarios=round(tasa_innecesarios, 2) if tasa_innecesarios is not None else None,
        uho_evaluables=uho_evaluables,
        ping_pongs=ping_pongs,
        tasa_hopp=round(tasa_hopp, 2) if tasa_hopp is not None else None,
        cambios_celda_no_observados=cambios_celda_no_observados,
        celdas_distintas=celdas_distintas,
    )




def calcular_distribucion_horaria(
    fecha_inicio: date,
    fecha_fin: date,
    repositorio: KpisRepository,
    tecnologia: list[int] | None = None,
    franja: list[str] | None = None,
    sesion_label: list[int] | None = None,
) -> list[HourlyDistributionResponse]:

    """Distribución de eventos de handover por hora del día (0-23), con el
    desglose de las 4 categorías en cada hora -- no solo el total, para que
    el frontend pueda graficar exitosos/fallidos/ping-pong/indeterminados
    juntos en vez de un único valor agregado.
    """
    secuencia = repositorio.obtener_secuencia_completa(fecha_inicio, fecha_fin, sesion_label)
    eventos_detectados, _ = _detectar_eventos_handover(secuencia)
    eventos = _filtrar_por_tecnologia(eventos_detectados, tecnologia)
    eventos = _filtrar_por_franja(eventos, franja)
    grupos = _agrupar_eventos(eventos, lambda evento: evento["timestamp"].hour)
    mediciones_por_hora = _contar_mediciones_por_clave(
        secuencia, tecnologia, franja, lambda timestamp_local: timestamp_local.hour
    )

    return [
        HourlyDistributionResponse(
            hora=hora,
            **grupos.get(hora, _CONTADOR_VACIO),
            total_mediciones=mediciones_por_hora.get(hora, 0),
        )
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


def _filtrar_por_franja(eventos: list[dict], franjas: list[str] | None) -> list[dict]:
    """Filtra una lista de eventos de handover ya detectados, quedándose
    solo con los que ocurrieron dentro de alguna de las franjas horarias
    pedidas. Una lista vacía o None se trata como "todas" (sin filtro).

    Se aplica DESPUÉS de `_detectar_eventos_handover`, nunca antes: filtrar
    la secuencia cruda de mediciones antes de detectar transiciones podría
    generar handovers falsos entre mediciones que en la realidad no eran
    consecutivas (con huecos de horas fuera de la franja de por medio).
    """
    if not franjas:
        return eventos
    conjunto = set(franjas)
    return [evento for evento in eventos if _franja_horaria(evento["timestamp"].hour) in conjunto]



def calcular_distribucion_franja_horaria(
    fecha_inicio: date,
    fecha_fin: date,
    repositorio: KpisRepository,
    tecnologia: list[int] | None = None,
    sesion_label: list[int] | None = None,
) -> list[FranjaHorariaResponse]:

    """Igual que `calcular_distribucion_horaria`, pero agrupado en 3 franjas
    en vez de 24 horas individuales."""
    secuencia = repositorio.obtener_secuencia_completa(fecha_inicio, fecha_fin, sesion_label)
    eventos, _ = _detectar_eventos_handover(secuencia)
    eventos = _filtrar_por_tecnologia(eventos, tecnologia)
    grupos = _agrupar_eventos(eventos, lambda evento: _franja_horaria(evento["timestamp"].hour))
    mediciones_por_franja = _contar_mediciones_por_clave(
        secuencia, tecnologia, None, lambda timestamp_local: _franja_horaria(timestamp_local.hour)
    )

    return [
        FranjaHorariaResponse(
            franja=franja,
            **grupos.get(franja, _CONTADOR_VACIO),
            total_mediciones=mediciones_por_franja.get(franja, 0),
        )
        for franja in FRANJAS_VALIDAS
    ]


def _dia_semana(timestamp) -> int:
    """Día de la semana de un timestamp: 0=Lunes ... 6=Domingo
    (`datetime.weekday()`, no `isoweekday()` -- así el índice empieza en 0
    y calza directo con `DIAS_SEMANA_ETIQUETAS`)."""
    return timestamp.weekday()


def calcular_distribucion_dia_semana(
    fecha_inicio: date,
    fecha_fin: date,
    repositorio: KpisRepository,
    tecnologia: list[int] | None = None,
    franja: list[str] | None = None,
    sesion_label: list[int] | None = None,
) -> list[DiaSemanaResponse]:

    """Distribución de eventos de handover por día de la semana (Lunes a
    Domingo), con el mismo desglose de categorías que las demás
    distribuciones.

    A diferencia de `calcular_distribucion_franja_horaria` (que ignora el
    filtro global de franja horaria a propósito, por ser la misma
    dimensión), esta función sí respeta `franja` y `tecnologia`: día de la
    semana es una dimensión distinta a hora del día, no hay conflicto
    conceptual en filtrar por ambas a la vez.
    """
    secuencia = repositorio.obtener_secuencia_completa(fecha_inicio, fecha_fin, sesion_label)
    eventos_detectados, _ = _detectar_eventos_handover(secuencia)
    eventos = _filtrar_por_tecnologia(eventos_detectados, tecnologia)
    eventos = _filtrar_por_franja(eventos, franja)
    grupos = _agrupar_eventos(eventos, lambda evento: _dia_semana(evento["timestamp"]))
    mediciones_por_dia = _contar_mediciones_por_clave(
        secuencia, tecnologia, franja, lambda timestamp_local: _dia_semana(timestamp_local)
    )

    return [
        DiaSemanaResponse(
            dia=dia,
            etiqueta=DIAS_SEMANA_ETIQUETAS[dia],
            **grupos.get(dia, _CONTADOR_VACIO),
            total_mediciones=mediciones_por_dia.get(dia, 0),
        )
        for dia in DIAS_SEMANA_ORDEN

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
        return  f"{dia}/{mes}/{anio[2:]}" 
    if periodo == "semanal":
        anio, semana = clave.split("-W")
        return f"Sem {semana}/{anio}"
    if periodo == "mensual":
        anio, mes = clave.split("-")
        return f"{mes}/{anio}"
    return clave  # anual: la propia clave ya es el año


def _limites_periodo(clave: str, periodo: str) -> tuple[date, date]:
    """Calcula las fechas de inicio y fin que delimitan un periodo, a partir
    de su clave de agrupación (ver `_clave_periodo`) -- para que la tabla
    por periodo (Paso 9 del plan de refactor) pueda mostrar el rango exacto
    de cada fila, no solo la etiqueta.
    """
    if periodo == "diario":
        fecha = date.fromisoformat(clave)
        return fecha, fecha
    if periodo == "semanal":
        anio, semana = (int(valor) for valor in clave.split("-W"))
        return date.fromisocalendar(anio, semana, 1), date.fromisocalendar(anio, semana, 7)
    if periodo == "mensual":
        anio, mes = (int(valor) for valor in clave.split("-"))
        ultimo_dia = calendar.monthrange(anio, mes)[1]
        return date(anio, mes, 1), date(anio, mes, ultimo_dia)
    anio = int(clave)  # anual
    return date(anio, 1, 1), date(anio, 12, 31)


def _contar_mediciones_por_clave(
    secuencia: list[tuple],
    tecnologia: list[int] | None,
    franjas: list[str] | None,
    funcion_clave: Callable[[object], str | int],
) -> dict[str | int, int]:
    """Cuenta mediciones CRUDAS (no eventos de handover) agrupadas por
    `funcion_clave`, aplicada sobre el timestamp ya convertido a hora local.

    A diferencia de `_agrupar_eventos` (que cuenta handovers detectados),
    esto cuenta cada fila de la secuencia -- necesario para mostrar "cuántas
    mediciones hay" junto a "cuántos handovers" en el tooltip de los
    gráficos de distribución y en la tabla de tendencia (Paso 9 del plan de
    refactor). Respeta los mismos filtros de tecnología y franja que ya se
    aplican a los eventos, para que el número no contradiga lo que se ve en
    el resto del gráfico/tabla.
    """
    conjunto_tecnologia = set(tecnologia) if tecnologia else None
    conjunto_franjas = set(franjas) if franjas else None
    conteos: dict[str | int, int] = {}
    for registro in secuencia:
        if conjunto_tecnologia is not None and registro[7] not in conjunto_tecnologia:
            continue
        timestamp_local = registro[1].astimezone(ZONA_HORARIA_ORIGEN)
        if conjunto_franjas is not None and _franja_horaria(timestamp_local.hour) not in conjunto_franjas:
            continue
        clave = funcion_clave(timestamp_local)
        conteos[clave] = conteos.get(clave, 0) + 1
    return conteos


def calcular_tendencia(
    fecha_inicio: date,
    fecha_fin: date,
    repositorio: KpisRepository,
    periodo: str = "diario",
    tecnologia: list[int] | None = None,
    franja: list[str] | None = None,
    sesion_label: list[int] | None = None,
) -> list[TrendResponse]:

    """Evolución de los KPIs de handover a lo largo del tiempo, agrupada por
    `periodo` (diario/semanal/mensual/anual -- ver `PERIODOS_VALIDOS`).

    Cada punto trae, además de los conteos, las fechas que delimitan ese
    periodo (`fecha_inicio`/`fecha_fin`, vía `_limites_periodo`) y el total
    de mediciones de ese periodo (no solo de handovers) -- Paso 9 del plan
    de refactor, pensado para la tabla por periodo del frontend.
    """
    secuencia = repositorio.obtener_secuencia_completa(fecha_inicio, fecha_fin, sesion_label)
    eventos_detectados, _ = _detectar_eventos_handover(secuencia)
    eventos = _filtrar_por_tecnologia(eventos_detectados, tecnologia)
    eventos = _filtrar_por_franja(eventos, franja)
    grupos = _agrupar_eventos(eventos, lambda evento: _clave_periodo(evento["timestamp"], periodo))
    mediciones_por_periodo = _contar_mediciones_por_clave(
        secuencia, tecnologia, franja, lambda timestamp_local: _clave_periodo(timestamp_local, periodo)
    )

    resultado = []
    for clave in sorted(grupos):
        valores = grupos[clave]
        exitosos, fallidos = valores["exitosos"], valores["fallidos"]
        clasificados = exitosos + fallidos
        tasa_exito = (exitosos / clasificados * 100) if clasificados > 0 else None
        tasa_phd = (fallidos / clasificados * 100) if clasificados > 0 else None
        total_ho_periodo = valores["total"]
        tasa_hopp = (valores["ping_pongs"] / total_ho_periodo * 100) if total_ho_periodo > 0 else None
        uho_evaluables = valores["uho_evaluables"]
        tasa_innecesarios = (valores["uho_eventos"] / uho_evaluables * 100) if uho_evaluables > 0 else None
        fecha_inicio_periodo, fecha_fin_periodo = _limites_periodo(clave, periodo)

        resultado.append(
            TrendResponse(
                periodo=clave,
                etiqueta=_etiqueta_periodo(clave, periodo),
                fecha_inicio=fecha_inicio_periodo,
                fecha_fin=fecha_fin_periodo,
                total_mediciones=mediciones_por_periodo.get(clave, 0),
                total_handovers=total_ho_periodo,
                exitosos=exitosos,
                fallidos=fallidos,
                indeterminados=valores["indeterminados"],
                tasa_exito=round(tasa_exito, 2) if tasa_exito is not None else None,
                tasa_phd=round(tasa_phd, 2) if tasa_phd is not None else None,
                ping_pongs=valores["ping_pongs"],
                tasa_hopp=round(tasa_hopp, 2) if tasa_hopp is not None else None,
                uho_evaluables=uho_evaluables,
                uho=valores["uho_eventos"],
                tasa_innecesarios=round(tasa_innecesarios, 2) if tasa_innecesarios is not None else None,
            )
        )

    return resultado

