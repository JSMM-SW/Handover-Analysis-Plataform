"""
Pruebas unitarias de las reglas de negocio puras del módulo de KPIs
(`app.modules.kpis.services`): detección de handovers (por sesión y por
tramos), criterio PHD (éxito/fallo/indeterminado), criterio UHO (handover
innecesario), ping-pong, franjas horarias y claves/etiquetas de periodo.

Todas las funciones probadas aquí son funciones puras: reciben tuplas o
diccionarios y devuelven valores, sin base de datos ni FastAPI. Por eso
no se necesita ningún repositorio falso en este archivo -- eso queda para
`test_kpis_services.py`. Las pruebas que necesitan SQL real (orden por
report_index) están en `test_kpis_repository.py`.

Formato de cada medición (el mismo que devuelve
`KpisRepository.obtener_secuencia_completa`):
    (cell_id, timestamp_medicion, rsrp_dbm, rssi, rsrq, rssnr,
    execution_id, tecnologia, report_index)
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.modules.kpis.services import (
    EXITOSO,
    FALLIDO,
    INDETERMINADO,
    _agrupar_eventos,
    _clasificar_handover,
    _clave_periodo,
    _detectar_eventos_handover,
    _es_uho,
    _etiqueta_periodo,
    _filtrar_por_franja,
    _franja_horaria,
)


INSTANTE_BASE = datetime(2026, 5, 5, 8, 0, 0, tzinfo=timezone.utc)
SESION_A = uuid4()
SESION_B = uuid4()


def _medicion(
    celda: int,
    segundos: int = 0,
    rssi: int | None = -90,
    rsrq: int | None = -12,
    sesion=None,
    tecnologia: int = 1,
    report_index: int | None = None,
) -> tuple:
    """Construye una medición con el formato de
    `KpisRepository.obtener_secuencia_completa`.

    `segundos` se suma a `INSTANTE_BASE` para ordenar cronológicamente las
    mediciones dentro de una prueba. RSRP y RSSNR se dejan en None porque
    ninguna regla de KPIs de handover los usa (PHD y UHO solo usan RSSI y
    RSRQ). `sesion` por defecto es SESION_A -- la mayoría de las pruebas no
    les importa la sesión, solo las que prueban agrupación (ver más abajo).
    """
    return (
        celda,
        INSTANTE_BASE + timedelta(seconds=segundos),
        None,
        rssi,
        rsrq,
        None,
        sesion or SESION_A,
        tecnologia,
        report_index,
    )


def _secuencia_de_celdas(*celdas: int) -> list[tuple]:
    """Construye una secuencia cronológica (una medición por segundo, misma
    sesión) a partir de una lista de celdas, con los mismos valores de
    señal en todas. Útil cuando la prueba solo verifica la detección o el
    ping-pong, no la clasificación PHD/UHO ni la agrupación por sesión."""
    return [_medicion(celda, segundos=indice) for indice, celda in enumerate(celdas)]


# ---------------------------------------------------------------------------
# Criterio PHD: _clasificar_handover
# ---------------------------------------------------------------------------


def test_phd_exitoso_cuando_rssi_y_rsrq_mejoran():
    """Si RSSI y RSRQ mejoran en la celda de destino, PHD no se cumple y el
    handover es exitoso."""
    origen = _medicion(1, rssi=-90, rsrq=-12)
    destino = _medicion(2, rssi=-80, rsrq=-10)

    assert _clasificar_handover(origen, destino) == EXITOSO


def test_phd_fallido_cuando_rssi_se_mantiene_igual():
    """Asimetría intencional de PHD: en RSSI el operador es <=, así que
    quedarse exactamente igual ya cuenta como degradación (aunque RSRQ
    mejore)."""
    origen = _medicion(1, rssi=-90, rsrq=-12)
    destino = _medicion(2, rssi=-90, rsrq=-10)

    assert _clasificar_handover(origen, destino) == FALLIDO


def test_phd_exitoso_cuando_rsrq_se_mantiene_igual_y_rssi_mejora():
    """Asimetría intencional de PHD: en RSRQ el operador es < estricto, así
    que quedarse igual NO cuenta como degradación."""
    origen = _medicion(1, rssi=-90, rsrq=-12)
    destino = _medicion(2, rssi=-80, rsrq=-12)

    assert _clasificar_handover(origen, destino) == EXITOSO


def test_phd_fallido_cuando_solo_rsrq_empeora():
    """PHD usa OR: basta con que RSRQ empeore para que el handover sea
    fallido, aunque RSSI haya mejorado."""
    origen = _medicion(1, rssi=-90, rsrq=-12)
    destino = _medicion(2, rssi=-80, rsrq=-14)

    assert _clasificar_handover(origen, destino) == FALLIDO


def test_phd_fallido_cuando_solo_rssi_empeora():
    """PHD usa OR: basta con que RSSI empeore para que el handover sea
    fallido, aunque RSRQ haya mejorado."""
    origen = _medicion(1, rssi=-90, rsrq=-12)
    destino = _medicion(2, rssi=-95, rsrq=-10)

    assert _clasificar_handover(origen, destino) == FALLIDO


@pytest.mark.parametrize(
    "rssi_origen, rsrq_origen, rssi_destino, rsrq_destino",
    [
        (None, -12, -80, -10),
        (-90, None, -80, -10),
        (-90, -12, None, -10),
        (-90, -12, -80, None),
        (None, None, None, None),
    ],
)
def test_phd_indeterminado_si_falta_algun_valor(rssi_origen, rsrq_origen, rssi_destino, rsrq_destino):
    """Si falta RSSI o RSRQ en cualquiera de los dos lados de la transición,
    no hay evidencia para clasificar: el handover queda indeterminado."""
    origen = _medicion(1, rssi=rssi_origen, rsrq=rsrq_origen)
    destino = _medicion(2, rssi=rssi_destino, rsrq=rsrq_destino)

    assert _clasificar_handover(origen, destino) == INDETERMINADO


# ---------------------------------------------------------------------------
# Criterio UHO: _es_uho
# ---------------------------------------------------------------------------


def test_uho_verdadero_justo_en_los_umbrales():
    """Los umbrales de UHO son inclusivos (>=): RSSI = -100 dBm y
    RSRQ = -15 dB ya cuentan como señal suficientemente buena."""
    assert _es_uho(_medicion(1, rssi=-100, rsrq=-15)) is True


def test_uho_falso_si_rssi_esta_bajo_el_umbral():
    """Con RSSI de origen por debajo de -100 dBm el salto sí hacía falta."""
    assert _es_uho(_medicion(1, rssi=-101, rsrq=-10)) is False


def test_uho_falso_si_rsrq_esta_bajo_el_umbral():
    """Con RSRQ de origen por debajo de -15 dB el salto sí hacía falta."""
    assert _es_uho(_medicion(1, rssi=-80, rsrq=-16)) is False


@pytest.mark.parametrize("rssi, rsrq", [(None, -10), (-80, None), (None, None)])
def test_uho_no_evaluable_si_falta_algun_valor(rssi, rsrq):
    """Sin RSSI o RSRQ de origen no se puede evaluar UHO: devuelve None (ni
    UHO ni "no UHO"), para quedar fuera del denominador de la tasa."""
    assert _es_uho(_medicion(1, rssi=rssi, rsrq=rsrq)) is None


# ---------------------------------------------------------------------------
# Detección de eventos: _detectar_eventos_handover
# ---------------------------------------------------------------------------


def test_deteccion_secuencia_vacia_no_genera_eventos():
    """Sin mediciones no hay transiciones de celda."""
    eventos, cambios = _detectar_eventos_handover([])
    assert eventos == []
    assert cambios == 0


def test_deteccion_sin_cambio_de_celda_no_genera_eventos():
    """Varias mediciones en la misma celda no son un handover."""
    eventos, _ = _detectar_eventos_handover(_secuencia_de_celdas(10, 10, 10))
    assert eventos == []


def test_deteccion_un_cambio_de_celda_genera_un_evento_anclado_en_el_destino():
    """Un cambio de celda genera exactamente un evento, con la celda y el
    timestamp de la PRIMERA medición en la celda de destino."""
    secuencia = _secuencia_de_celdas(10, 10, 20, 20)

    eventos, _ = _detectar_eventos_handover(secuencia)

    assert len(eventos) == 1
    assert eventos[0]["celda"] == 20
    assert eventos[0]["timestamp"] == secuencia[2][1]
    assert eventos[0]["ping_pong"] is False


def test_deteccion_clasifica_con_la_medicion_inmediatamente_anterior():
    """El origen de PHD/UHO es la ÚLTIMA medición antes del cambio, no la
    primera medición en la celda de origen."""
    secuencia = [
        _medicion(10, segundos=0, rssi=-100, rsrq=-12),
        _medicion(10, segundos=1, rssi=-70, rsrq=-12),
        _medicion(20, segundos=2, rssi=-80, rsrq=-10),
    ]

    eventos, _ = _detectar_eventos_handover(secuencia)

    # Contra -70 dBm (última medición de origen) el RSSI empeoró -> fallido.
    # Si se usara -100 dBm (primera medición) saldría exitoso.
    assert eventos[0]["clasificacion"] == FALLIDO


def test_deteccion_uho_se_evalua_solo_con_la_celda_de_origen():
    """UHO mira únicamente el origen: aunque el destino tenga señal muy
    mala, si el origen ya era bueno el handover es innecesario."""
    secuencia = [
        _medicion(10, segundos=0, rssi=-80, rsrq=-10),
        _medicion(20, segundos=1, rssi=-120, rsrq=-20),
    ]

    eventos, _ = _detectar_eventos_handover(secuencia)

    assert eventos[0]["uho"] is True
    assert eventos[0]["clasificacion"] == FALLIDO  # UHO y PHD son independientes


def test_ping_pong_patron_a_b_a():
    """A -> B -> A: el segundo handover (vuelta a A) es ping-pong; el
    primero no."""
    eventos, _ = _detectar_eventos_handover(_secuencia_de_celdas(1, 2, 1))

    assert [evento["ping_pong"] for evento in eventos] == [False, True]


def test_ping_pong_no_se_marca_si_no_vuelve_a_la_celda_anterior():
    """A -> B -> C no es ping-pong."""
    eventos, _ = _detectar_eventos_handover(_secuencia_de_celdas(1, 2, 3))

    assert [evento["ping_pong"] for evento in eventos] == [False, False]


def test_ping_pong_oscilacion_continua():
    """A -> B -> A -> B: el segundo y el tercer handover son ping-pong."""
    eventos, _ = _detectar_eventos_handover(_secuencia_de_celdas(1, 2, 1, 2))

    assert [evento["ping_pong"] for evento in eventos] == [False, True, True]


def test_ping_pong_se_evalua_sobre_celdas_visitadas_no_sobre_mediciones():
    """Mediciones repetidas en la misma celda no rompen el patrón:
    A, A, B, B, B, A sigue siendo A -> B -> A."""
    eventos, _ = _detectar_eventos_handover(_secuencia_de_celdas(1, 1, 2, 2, 2, 1))

    assert [evento["ping_pong"] for evento in eventos] == [False, True]


# ---------------------------------------------------------------------------
# Sesiones y tramos (Paso 2): _detectar_eventos_handover
# ---------------------------------------------------------------------------


def test_deteccion_no_cruza_entre_sesiones_distintas():
    """Dos sesiones distintas nunca generan un handover entre ellas, aunque
    terminen y empiecen en celdas diferentes y estén "pegadas" en el
    tiempo -- cada sesión es una grabación independiente."""
    secuencia = [
        _medicion(10, segundos=0, sesion=SESION_A),
        _medicion(20, segundos=1, sesion=SESION_A),
        _medicion(99, segundos=2, sesion=SESION_B),
        _medicion(88, segundos=3, sesion=SESION_B),
    ]

    eventos, cambios = _detectar_eventos_handover(secuencia)

    assert [evento["celda"] for evento in eventos] == [20, 88]
    assert cambios == 0  # el corte es de sesión, no de hueco


def test_deteccion_sesiones_solapadas_no_generan_handovers_cruzados():
    """Dos sesiones que se grabaron en paralelo (sus mediciones se
    intercalan en el tiempo) no se mezclan: la secuencia llega agrupada
    por sesión (ver KpisRepository.obtener_secuencia_completa), así que
    nunca se compara una medición de A contra una de B aunque por
    timestamp real queden intercaladas."""
    secuencia = [
        _medicion(10, segundos=0, sesion=SESION_A),
        _medicion(20, segundos=10, sesion=SESION_A),
        _medicion(50, segundos=5, sesion=SESION_B),
        _medicion(60, segundos=15, sesion=SESION_B),
    ]

    eventos, cambios = _detectar_eventos_handover(secuencia)

    assert {evento["celda"] for evento in eventos} == {20, 60}
    assert cambios == 0


def test_deteccion_corte_por_hueco_mayor_a_10_segundos_no_cuenta():
    """Un hueco de 11 s entre mediciones consecutivas de la misma sesión
    corta la secuencia: el cambio de celda no se cuenta como handover,
    pero sí se registra como cambio de celda no observado."""
    secuencia = [_medicion(10, segundos=0), _medicion(20, segundos=11)]

    eventos, cambios = _detectar_eventos_handover(secuencia)

    assert eventos == []
    assert cambios == 1


def test_deteccion_hueco_de_exactamente_10_segundos_si_cuenta():
    """El límite es estrictamente mayor a 10 s: un hueco de exactamente
    10 s no corta la secuencia."""
    secuencia = [_medicion(10, segundos=0), _medicion(20, segundos=10)]

    eventos, cambios = _detectar_eventos_handover(secuencia)

    assert len(eventos) == 1
    assert eventos[0]["celda"] == 20
    assert cambios == 0


def test_cambios_celda_no_observados_no_cuenta_sin_cambio_de_celda():
    """Un hueco largo sin cambio de celda no suma a
    cambios_celda_no_observados -- no hay evidencia de que algo se haya
    perdido."""
    secuencia = [_medicion(10, segundos=0), _medicion(10, segundos=20)]

    eventos, cambios = _detectar_eventos_handover(secuencia)

    assert eventos == []
    assert cambios == 0


def test_ping_pong_no_se_encadena_a_traves_de_un_corte_por_hueco():
    """A -> B, hueco de 11 s, B -> A: el patrón visual sigue siendo
    A-B-A, pero como el segundo salto quedó en un tramo distinto (el
    hueco lo cortó), ni siquiera se detecta como handover -- y por lo
    tanto tampoco puede marcarse como ping-pong."""
    secuencia = [
        _medicion(1, segundos=0),
        _medicion(2, segundos=1),
        _medicion(1, segundos=12),  # 11 s después de la medición anterior
    ]

    eventos, cambios = _detectar_eventos_handover(secuencia)

    assert len(eventos) == 1  # solo 1->2; el 2->1 quedó cortado por el hueco
    assert eventos[0]["ping_pong"] is False
    assert cambios == 1  # el corte sí tenía cambio de celda (2 -> 1)


# ---------------------------------------------------------------------------
# Franjas horarias: _franja_horaria y _filtrar_por_franja
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hora, franja_esperada",
    [
        (0, "noche"),
        (5, "noche"),
        (6, "manana"),
        (11, "manana"),
        (12, "tarde"),
        (18, "tarde"),
        (19, "noche"),
        (23, "noche"),
    ],
)
def test_franja_horaria_limites(hora, franja_esperada):
    """Verifica los límites exactos de cada franja: mañana 06-11,
    tarde 12-18, noche 19-05 (envuelve la medianoche)."""
    assert _franja_horaria(hora) == franja_esperada


def test_filtrar_por_franja_sin_franja_devuelve_todos_los_eventos():
    """Si no se pide franja, la lista se devuelve sin filtrar."""
    eventos = [{"timestamp": INSTANTE_BASE.replace(hour=hora)} for hora in (3, 9, 15)]

    assert _filtrar_por_franja(eventos, None) == eventos


def test_filtrar_por_franja_conserva_solo_los_eventos_de_esa_franja():
    """Con franja 'tarde' solo quedan los eventos entre las 12:00 y las
    18:59."""
    eventos = [{"timestamp": INSTANTE_BASE.replace(hour=hora)} for hora in (3, 9, 12, 18, 19)]

    filtrados = _filtrar_por_franja(eventos, ["tarde"])

    assert [evento["timestamp"].hour for evento in filtrados] == [12, 18]


# ---------------------------------------------------------------------------
# Agrupación: _agrupar_eventos
# ---------------------------------------------------------------------------


def test_agrupar_eventos_cuenta_cada_categoria_por_grupo():
    """Cada grupo acumula total, exitosos, fallidos, indeterminados y
    ping-pongs de forma independiente."""
    eventos = [
        {"grupo": "a", "clasificacion": EXITOSO, "ping_pong": False},
        {"grupo": "a", "clasificacion": FALLIDO, "ping_pong": True},
        {"grupo": "a", "clasificacion": INDETERMINADO, "ping_pong": False},
        {"grupo": "b", "clasificacion": EXITOSO, "ping_pong": True},
    ]

    grupos = _agrupar_eventos(eventos, lambda evento: evento["grupo"])

    assert grupos["a"] == {"total": 3, "exitosos": 1, "fallidos": 1, "indeterminados": 1, "ping_pongs": 1}
    assert grupos["b"] == {"total": 1, "exitosos": 1, "fallidos": 0, "indeterminados": 0, "ping_pongs": 1}


# ---------------------------------------------------------------------------
# Periodos de tendencia: _clave_periodo y _etiqueta_periodo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "periodo, clave_esperada",
    [
        ("diario", "2026-05-05"),
        ("semanal", "2026-W19"),
        ("mensual", "2026-05"),
        ("anual", "2026"),
    ],
)
def test_clave_periodo(periodo, clave_esperada):
    """Cada periodicidad produce una clave ordenable alfabéticamente."""
    assert _clave_periodo(INSTANTE_BASE, periodo) == clave_esperada


def test_clave_periodo_semanal_usa_calendario_iso_en_cambio_de_anio():
    """El 1 de enero de 2027 (viernes) pertenece a la semana ISO 53 de
    2026, no a la semana 0 de 2027 -- por eso se usa `isocalendar()` y no
    `strftime('%W')`."""
    primero_de_enero = datetime(2027, 1, 1, 12, 0, tzinfo=timezone.utc)

    assert _clave_periodo(primero_de_enero, "semanal") == "2026-W53"


@pytest.mark.parametrize(
    "clave, periodo, etiqueta_esperada",
    [
        ("2026-05-05", "diario", "05/05/26"),
        ("2026-W19", "semanal", "Sem 19/2026"),
        ("2026-05", "mensual", "05/2026"),
        ("2026", "anual", "2026"),
    ],
)
def test_etiqueta_periodo(clave, periodo, etiqueta_esperada):
    """La etiqueta legible del eje de la gráfica corresponde a cada clave
    técnica."""
    assert _etiqueta_periodo(clave, periodo) == etiqueta_esperada
