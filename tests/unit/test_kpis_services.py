"""
Pruebas unitarias de las funciones públicas del módulo de KPIs
(`app.modules.kpis.services`): las que usan los endpoints de
`/api/v1/kpis`.

Estas funciones reciben un `KpisRepository`, pero en las pruebas se les
pasa un repositorio falso (`RepositorioKpisFalso`) que devuelve datos
fijos en memoria. Así se prueba la lógica del servicio (cálculo de tasas,
filtros, agrupaciones, armado de las respuestas Pydantic) sin conectarse
a Supabase -- gracias al Repository Pattern, el servicio no sabe ni le
importa de dónde vienen los datos.

Las reglas puras (PHD, UHO, ping-pong, franjas) ya se prueban una por una
en `test_kpis_reglas.py`; aquí se verifica que los servicios las combinan
correctamente.
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.modules.kpis.services import (
    calcular_distribucion_dia_semana,
    calcular_distribucion_franja_horaria,
    calcular_distribucion_horaria,
    calcular_metricas_globales_dia,
    calcular_resumen_kpis,
    calcular_tendencia,
    listar_sesiones,
)


FECHA_INICIO = date(2026, 5, 5)
FECHA_FIN = date(2026, 5, 6)


class RepositorioKpisFalso:
    """Sustituto en memoria de `KpisRepository` para las pruebas.

    Devuelve siempre los datos que recibe en el constructor y guarda en
    `llamadas` los argumentos con los que el servicio lo invocó, para poder
    verificar que los filtros se pasan correctamente a la capa de datos.
    """

    def __init__(
        self,
        secuencia: list[tuple] | None = None,
        total_mediciones: int = 0,
        metricas_diarias: dict | None = None,
        sesiones: list | None = None,
    ):
        """Guarda los datos fijos que devolverá cada método."""
        self.secuencia = secuencia or []
        self.total_mediciones = total_mediciones
        self.metricas_diarias = metricas_diarias
        self.sesiones = sesiones or []
        self.llamadas: dict[str, tuple] = {}

    def obtener_secuencia_completa(self, fecha_inicio, fecha_fin, tecnologia=None, sesion_label=None):
        """Imita `KpisRepository.obtener_secuencia_completa`."""
        self.llamadas["obtener_secuencia_completa"] = (fecha_inicio, fecha_fin, tecnologia, sesion_label)
        return self.secuencia

    def contar_mediciones(self, fecha_inicio, fecha_fin, tecnologia=None, franja=None, sesion_label=None):
        """Imita `KpisRepository.contar_mediciones`."""
        self.llamadas["contar_mediciones"] = (fecha_inicio, fecha_fin, tecnologia, franja, sesion_label)
        return self.total_mediciones

    def obtener_metricas_diarias_senal(self, fecha):
        """Imita `KpisRepository.obtener_metricas_diarias_senal`."""
        self.llamadas["obtener_metricas_diarias_senal"] = (fecha,)
        return self.metricas_diarias

    def listar_sesiones(self):
        """Imita `KpisRepository.listar_sesiones`."""
        return self.sesiones


def _medicion(celda: int, instante: datetime, rssi: int | None, rsrq: int | None) -> tuple:
    """Construye una medición con el formato de
    `KpisRepository.obtener_secuencia_completa`:
    (cell_id, timestamp_medicion, rsrp_dbm, rssi, rsrq, rssnr).
    """
    return (celda, instante, None, rssi, rsrq, None)


def _hora(dia: int, hora: int, minuto: int = 0) -> datetime:
    """Instante UTC de mayo de 2026, para escribir las secuencias de forma
    compacta."""
    return datetime(2026, 5, dia, hora, minuto, tzinfo=timezone.utc)


def _secuencia_escenario() -> list[tuple]:
    """Secuencia del martes 05/05/2026 con un caso de cada categoría.

    Recorrido de celdas: 1 -> 2 -> 1 -> 3 -> 4, que genera 4 handovers:

    | Hora  | Salto | PHD           | UHO (origen)       | Ping-pong |
    |-------|-------|---------------|--------------------|-----------|
    | 08:01 | 1->2  | exitoso       | True  (-95, -14)   | No        |
    | 13:00 | 2->1  | fallido       | True  (-85, -12)   | Sí        |
    | 20:00 | 1->3  | indeterminado | False (-105, -13)  | No        |
    | 21:00 | 3->4  | indeterminado | None (sin datos)   | No        |
    """
    return [
        _medicion(1, _hora(5, 8, 0), rssi=-95, rsrq=-14),
        _medicion(2, _hora(5, 8, 1), rssi=-85, rsrq=-12),
        _medicion(1, _hora(5, 13, 0), rssi=-105, rsrq=-13),
        _medicion(3, _hora(5, 20, 0), rssi=None, rsrq=None),
        _medicion(3, _hora(5, 20, 5), rssi=None, rsrq=None),
        _medicion(4, _hora(5, 21, 0), rssi=-80, rsrq=-10),
    ]


# ---------------------------------------------------------------------------
# calcular_resumen_kpis (GET /kpis/summary)
# ---------------------------------------------------------------------------


def test_resumen_calcula_conteos_y_tasas_del_escenario():
    """Sobre el escenario conocido, cada conteo y cada tasa coinciden con
    el cálculo hecho a mano (ver tabla en `_secuencia_escenario`)."""
    repositorio = RepositorioKpisFalso(secuencia=_secuencia_escenario(), total_mediciones=10)

    resumen = calcular_resumen_kpis(FECHA_INICIO, FECHA_FIN, repositorio)

    assert resumen.total_mediciones == 10
    assert resumen.total_handovers == 4
    assert resumen.tasa_handover == 40.0  # 4 / 10
    assert resumen.exitosos == 1
    assert resumen.fallidos == 1
    assert resumen.indeterminados == 2
    assert resumen.tasa_exito == 50.0  # 1 / (1 + 1): indeterminados fuera
    assert resumen.ping_pongs == 1
    assert resumen.tasa_hopp == 25.0  # 1 / 4
    assert resumen.tasa_innecesarios == 66.67  # 2 UHO / 3 evaluables


def test_resumen_sin_datos_devuelve_ceros_sin_dividir_por_cero():
    """Sin mediciones ni handovers todas las tasas valen 0 en vez de lanzar
    ZeroDivisionError."""
    repositorio = RepositorioKpisFalso(secuencia=[], total_mediciones=0)

    resumen = calcular_resumen_kpis(FECHA_INICIO, FECHA_FIN, repositorio)

    assert resumen.total_handovers == 0
    assert resumen.tasa_handover == 0.0
    assert resumen.tasa_exito == 0.0
    assert resumen.tasa_hopp == 0.0
    assert resumen.tasa_innecesarios == 0.0


def test_resumen_solo_indeterminados_deja_tasa_exito_en_cero():
    """Si ningún handover se pudo clasificar, el denominador de la tasa de
    éxito es 0 y la tasa vale 0 (no se cuentan indeterminados)."""
    secuencia = [
        _medicion(1, _hora(5, 8, 0), rssi=None, rsrq=None),
        _medicion(2, _hora(5, 8, 1), rssi=None, rsrq=None),
    ]
    repositorio = RepositorioKpisFalso(secuencia=secuencia, total_mediciones=2)

    resumen = calcular_resumen_kpis(FECHA_INICIO, FECHA_FIN, repositorio)

    assert resumen.total_handovers == 1
    assert resumen.indeterminados == 1
    assert resumen.tasa_exito == 0.0
    assert resumen.tasa_innecesarios == 0.0


def test_resumen_pasa_los_filtros_al_repositorio():
    """La franja horaria NO se pasa a la consulta de la secuencia (se
    aplica después de detectar eventos), pero sí al conteo de mediciones.
    Tecnología y sesión se pasan a ambas consultas."""
    repositorio = RepositorioKpisFalso()

    calcular_resumen_kpis(FECHA_INICIO, FECHA_FIN, repositorio, tecnologia=1, franja="tarde", sesion_label=7)

    assert repositorio.llamadas["obtener_secuencia_completa"] == (FECHA_INICIO, FECHA_FIN, 1, 7)
    assert repositorio.llamadas["contar_mediciones"] == (FECHA_INICIO, FECHA_FIN, 1, "tarde", 7)


def test_resumen_con_franja_cuenta_solo_los_eventos_de_esa_franja():
    """Con franja 'noche' solo quedan los dos handovers de las 20:00 y las
    21:00 del escenario."""
    repositorio = RepositorioKpisFalso(secuencia=_secuencia_escenario(), total_mediciones=4)

    resumen = calcular_resumen_kpis(FECHA_INICIO, FECHA_FIN, repositorio, franja="noche")

    assert resumen.total_handovers == 2
    assert resumen.indeterminados == 2
    assert resumen.ping_pongs == 0


def test_resumen_franja_se_aplica_despues_de_detectar_no_antes():
    """Caso que justifica filtrar DESPUÉS de detectar: el único cambio de
    celda real ocurre en la mañana (08:00). Si se filtraran primero las
    mediciones de la noche (05:00 en celda 1 y 19:30 en celda 2), parecerían
    consecutivas y aparecería un handover nocturno falso."""
    secuencia = [
        _medicion(1, _hora(5, 5, 0), rssi=-90, rsrq=-12),
        _medicion(2, _hora(5, 8, 0), rssi=-80, rsrq=-10),
        _medicion(2, _hora(5, 19, 30), rssi=-80, rsrq=-10),
    ]
    repositorio = RepositorioKpisFalso(secuencia=secuencia, total_mediciones=2)

    resumen = calcular_resumen_kpis(FECHA_INICIO, FECHA_FIN, repositorio, franja="noche")

    assert resumen.total_handovers == 0


# ---------------------------------------------------------------------------
# calcular_distribucion_horaria (GET /kpis/hourly)
# ---------------------------------------------------------------------------


def test_distribucion_horaria_devuelve_las_24_horas_con_su_desglose():
    """Siempre se devuelven las 24 horas (las vacías con ceros) y cada
    handover cae en la hora de su timestamp."""
    repositorio = RepositorioKpisFalso(secuencia=_secuencia_escenario())

    distribucion = calcular_distribucion_horaria(FECHA_INICIO, FECHA_FIN, repositorio)
    por_hora = {item.hora: item for item in distribucion}

    assert [item.hora for item in distribucion] == list(range(24))
    assert por_hora[8].total == 1 and por_hora[8].exitosos == 1
    assert por_hora[13].total == 1 and por_hora[13].fallidos == 1 and por_hora[13].ping_pongs == 1
    assert por_hora[20].indeterminados == 1
    assert por_hora[21].indeterminados == 1
    assert por_hora[0].total == 0
    assert sum(item.total for item in distribucion) == 4


def test_distribucion_horaria_respeta_el_filtro_de_franja():
    """Con franja 'manana' solo queda el handover de las 08:00."""
    repositorio = RepositorioKpisFalso(secuencia=_secuencia_escenario())

    distribucion = calcular_distribucion_horaria(FECHA_INICIO, FECHA_FIN, repositorio, franja="manana")

    assert sum(item.total for item in distribucion) == 1
    assert distribucion[8].total == 1


# ---------------------------------------------------------------------------
# calcular_distribucion_franja_horaria (GET /kpis/franja-horaria)
# ---------------------------------------------------------------------------


def test_distribucion_franja_devuelve_las_tres_franjas_en_orden():
    """Siempre devuelve mañana, tarde y noche en ese orden, con el
    desglose de cada una."""
    repositorio = RepositorioKpisFalso(secuencia=_secuencia_escenario())

    distribucion = calcular_distribucion_franja_horaria(FECHA_INICIO, FECHA_FIN, repositorio)

    assert [item.franja for item in distribucion] == ["manana", "tarde", "noche"]
    manana, tarde, noche = distribucion
    assert (manana.total, manana.exitosos) == (1, 1)
    assert (tarde.total, tarde.fallidos, tarde.ping_pongs) == (1, 1, 1)
    assert (noche.total, noche.indeterminados) == (2, 2)


def test_distribucion_franja_sin_datos_devuelve_ceros():
    """Sin handovers, las tres franjas aparecen igual, con total 0."""
    repositorio = RepositorioKpisFalso(secuencia=[])

    distribucion = calcular_distribucion_franja_horaria(FECHA_INICIO, FECHA_FIN, repositorio)

    assert [item.total for item in distribucion] == [0, 0, 0]


# ---------------------------------------------------------------------------
# calcular_distribucion_dia_semana (GET /kpis/dia-semana)
# ---------------------------------------------------------------------------


def test_distribucion_dia_semana_devuelve_lunes_a_domingo():
    """Devuelve los 7 días en orden con su etiqueta en español; el
    escenario ocurre el martes 05/05/2026."""
    repositorio = RepositorioKpisFalso(secuencia=_secuencia_escenario())

    distribucion = calcular_distribucion_dia_semana(FECHA_INICIO, FECHA_FIN, repositorio)

    assert [item.etiqueta for item in distribucion] == [
        "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo",
    ]
    assert distribucion[1].total == 4
    assert sum(item.total for item in distribucion) == 4


def test_distribucion_dia_semana_respeta_el_filtro_de_franja():
    """A diferencia de la distribución por franja, esta sí aplica el
    filtro global de franja horaria."""
    repositorio = RepositorioKpisFalso(secuencia=_secuencia_escenario())

    distribucion = calcular_distribucion_dia_semana(FECHA_INICIO, FECHA_FIN, repositorio, franja="tarde")

    assert distribucion[1].total == 1
    assert distribucion[1].fallidos == 1


# ---------------------------------------------------------------------------
# calcular_tendencia (GET /kpis/trend)
# ---------------------------------------------------------------------------


def _secuencia_dos_dias() -> list[tuple]:
    """Un handover exitoso el 05/05 (1 -> 2) y uno fallido con ping-pong el
    06/05 (2 -> 1)."""
    return [
        _medicion(1, _hora(5, 8, 0), rssi=-90, rsrq=-12),
        _medicion(2, _hora(5, 8, 1), rssi=-80, rsrq=-10),
        _medicion(1, _hora(6, 9, 0), rssi=-85, rsrq=-12),
    ]


def test_tendencia_diaria_un_punto_por_dia_ordenado():
    """Con periodo diario hay un punto por día con handovers, en orden
    cronológico, con su propia tasa de éxito."""
    repositorio = RepositorioKpisFalso(secuencia=_secuencia_dos_dias())

    tendencia = calcular_tendencia(FECHA_INICIO, FECHA_FIN, repositorio, periodo="diario")

    assert [(punto.periodo, punto.etiqueta) for punto in tendencia] == [
        ("2026-05-05", "05/05"),
        ("2026-05-06", "06/05"),
    ]
    primer_dia, segundo_dia = tendencia
    assert (primer_dia.exitosos, primer_dia.tasa_exito) == (1, 100.0)
    assert (segundo_dia.fallidos, segundo_dia.ping_pongs, segundo_dia.tasa_exito) == (1, 1, 0.0)


def test_tendencia_mensual_agrupa_todo_el_mes_en_un_punto():
    """Con periodo mensual, los dos días de mayo se juntan en un solo
    punto."""
    repositorio = RepositorioKpisFalso(secuencia=_secuencia_dos_dias())

    tendencia = calcular_tendencia(FECHA_INICIO, FECHA_FIN, repositorio, periodo="mensual")

    assert len(tendencia) == 1
    assert tendencia[0].etiqueta == "05/2026"
    assert tendencia[0].total_handovers == 2
    assert tendencia[0].tasa_exito == 50.0


def test_tendencia_sin_datos_devuelve_lista_vacia():
    """A diferencia de las distribuciones, la tendencia no rellena periodos
    vacíos: sin handovers devuelve una lista vacía."""
    repositorio = RepositorioKpisFalso(secuencia=[])

    assert calcular_tendencia(FECHA_INICIO, FECHA_FIN, repositorio) == []


# ---------------------------------------------------------------------------
# calcular_metricas_globales_dia (GET /kpis/daily)
# ---------------------------------------------------------------------------


def test_metricas_dia_calcula_tasa_de_riesgo_sobre_mediciones_con_rsrp():
    """La tasa de riesgo usa como denominador solo las mediciones que traen
    RSRP (80), no el total (100); los valores se redondean a 2 decimales."""
    repositorio = RepositorioKpisFalso(
        metricas_diarias={"total": 100, "total_rsrp": 80, "promedio": -95.456, "criticos": 20}
    )

    metricas = calcular_metricas_globales_dia(FECHA_INICIO, repositorio)

    assert metricas.fecha == FECHA_INICIO
    assert metricas.total_mediciones == 100
    assert metricas.promedio_rsrp == -95.46
    assert metricas.eventos_criticos == 20
    assert metricas.tasa_riesgo == 25.0  # 20 / 80


def test_metricas_dia_sin_rsrp_devuelve_nulos():
    """Si ninguna medición del día trae RSRP, el promedio y la tasa de
    riesgo quedan en None en vez de inventar un valor."""
    repositorio = RepositorioKpisFalso(
        metricas_diarias={"total": 50, "total_rsrp": 0, "promedio": None, "criticos": None}
    )

    metricas = calcular_metricas_globales_dia(FECHA_INICIO, repositorio)

    assert metricas.total_mediciones == 50
    assert metricas.promedio_rsrp is None
    assert metricas.tasa_riesgo is None


# ---------------------------------------------------------------------------
# listar_sesiones (GET /kpis/sesiones)
# ---------------------------------------------------------------------------


def test_listar_sesiones_convierte_cada_ejecucion_en_respuesta():
    """Cada ejecución del repositorio se convierte en un `SesionResponse`
    conservando el orden."""
    procesado = datetime(2026, 6, 23, 17, 0, tzinfo=timezone.utc)
    ejecuciones = [
        SimpleNamespace(sesion_label=2, filename="Session_43.csv", processing_date=procesado, records_valid=86000),
        SimpleNamespace(sesion_label=1, filename="Session_12.csv", processing_date=procesado, records_valid=500),
    ]
    repositorio = RepositorioKpisFalso(sesiones=ejecuciones)

    sesiones = listar_sesiones(repositorio)

    assert [sesion.sesion_label for sesion in sesiones] == [2, 1]
    assert sesiones[0].filename == "Session_43.csv"
    assert sesiones[0].records_valid == 86000
