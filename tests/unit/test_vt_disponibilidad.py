"""
Pruebas de la disponibilidad de datos y de los filtros de tiempo del Módulo 2.

Cubren lo que alimenta la configuración del análisis:

- las franjas horarias que ofrece el calendario, agrupando los minutos con mediciones;
- que la franja horaria se compare en la zona del usuario y no en UTC (regresión);
- que las tecnologías no estén fijadas en el código;
- los intervalos en minutos del histograma de radiobases repetidas, contados por sesión.
"""

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.modules.visualizacion_temporal.detector import Medicion
from app.modules.visualizacion_temporal.exceptions import SesionNoEncontrada
from app.modules.visualizacion_temporal.repository import VisualizacionTemporalRepository
from app.modules.visualizacion_temporal.schemas import FiltrosTemporales
from app.modules.visualizacion_temporal.services import (
    agrupar_en_franjas,
    obtener_celdas_repetidas,
    obtener_disponibilidad,
)

T0 = datetime(2026, 9, 28, 21, 24, 0, tzinfo=timezone.utc)


def minutos(*textos: str) -> list[time]:
    return [time.fromisoformat(t) for t in textos]


# ------------------------------------------------------------------------------ franjas


def test_minutos_seguidos_forman_una_sola_franja():
    franjas = agrupar_en_franjas(minutos("16:24", "16:25", "16:26", "16:27"))

    assert [(f.inicio, f.fin) for f in franjas] == [(time(16, 24), time(16, 27))]


def test_un_minuto_suelto_sin_datos_no_parte_la_franja():
    franjas = agrupar_en_franjas(minutos("16:24", "16:26"))

    assert len(franjas) == 1


def test_una_pausa_larga_separa_dos_franjas():
    franjas = agrupar_en_franjas(minutos("16:24", "16:25", "18:02", "18:03"))

    assert [(f.inicio, f.fin) for f in franjas] == [
        (time(16, 24), time(16, 25)),
        (time(18, 2), time(18, 3)),
    ]


def test_las_franjas_no_dependen_del_orden_ni_de_los_repetidos():
    franjas = agrupar_en_franjas(minutos("16:26", "16:24", "16:25", "16:25"))

    assert [(f.inicio, f.fin) for f in franjas] == [(time(16, 24), time(16, 26))]


# ------------------------------------------------------------------------------ disponibilidad


class RepositorioDisponibilidad:
    def __init__(self):
        self.zonas_pedidas = []

    def existe_sesion(self, sesion_id):
        return sesion_id in {"a", "b"}

    def contar_mediciones_por_minuto(self, sesion_ids, zona_horaria):
        self.zonas_pedidas.append(zona_horaria)
        return [
            {"fecha": date(2026, 10, 3), "minuto": time(9, 0), "n_mediciones": 50},
            {"fecha": date(2026, 9, 28), "minuto": time(16, 24), "n_mediciones": 60},
            {"fecha": date(2026, 9, 28), "minuto": time(16, 25), "n_mediciones": 58},
        ]

    def contar_handovers_por_dia(self, sesion_ids, zona_horaria):
        self.zonas_pedidas.append(zona_horaria)
        # Un día con eventos pero sin mediciones (sesión recargada) no debe aparecer.
        return [
            {"fecha": date(2026, 9, 28), "n_handovers": 39},
            {"fecha": date(2026, 1, 1), "n_handovers": 4},
        ]

    def listar_tecnologias(self, sesion_ids):
        return ["LTE", "NR"]


def test_la_disponibilidad_lista_los_dias_en_orden_con_sus_totales():
    repositorio = RepositorioDisponibilidad()
    filtros = FiltrosTemporales(sesion_ids=["a", "b"], zona_horaria="America/Guayaquil")

    salida = obtener_disponibilidad(filtros, repository=repositorio)

    assert [d.fecha for d in salida.dias] == [date(2026, 9, 28), date(2026, 10, 3)]
    assert salida.dias[0].n_mediciones == 118
    assert salida.dias[0].n_handovers == 39
    assert salida.dias[1].n_handovers == 0
    assert [(f.inicio, f.fin) for f in salida.dias[0].franjas] == [(time(16, 24), time(16, 25))]
    assert salida.zona_horaria == "America/Guayaquil"
    assert repositorio.zonas_pedidas == ["America/Guayaquil", "America/Guayaquil"]


def test_las_tecnologias_salen_de_los_datos_y_no_de_una_lista_fija():
    salida = obtener_disponibilidad(
        FiltrosTemporales(sesion_ids=["a"]), repository=RepositorioDisponibilidad()
    )

    assert salida.tecnologias == ["LTE", "NR"]


def test_la_disponibilidad_de_una_sesion_inexistente_avisa():
    with pytest.raises(SesionNoEncontrada):
        obtener_disponibilidad(
            FiltrosTemporales(sesion_ids=["x"]), repository=RepositorioDisponibilidad()
        )


# ------------------------------------------------------------------------------ filtros


def test_el_filtro_rechaza_una_zona_horaria_desconocida():
    with pytest.raises(ValueError, match="Zona horaria desconocida"):
        FiltrosTemporales(sesion_ids=["a"], zona_horaria="Marte/Olimpo")


def test_el_filtro_acepta_cualquier_tecnologia_bien_formada():
    filtros = FiltrosTemporales(sesion_ids=["a"], tecnologia=["LTE", "NR", "5G-NSA"])

    assert filtros.tecnologia == ["LTE", "NR", "5G-NSA"]


def test_el_filtro_rechaza_una_tecnologia_mal_formada():
    with pytest.raises(ValueError, match="Tecnología no válida"):
        FiltrosTemporales(sesion_ids=["a"], tecnologia=["LTE; DROP TABLE"])


def test_la_franja_horaria_se_compara_en_la_zona_del_usuario():
    """Regresión: `columna::time` daba la hora UTC y la franja local no encontraba nada."""
    filtros = SimpleNamespace(
        hora_inicio=time(16, 20), hora_fin=time(16, 50), zona_horaria="America/Guayaquil"
    )
    parametros: dict = {}

    condiciones = VisualizacionTemporalRepository._condiciones_de_hora(
        filtros, "timestamp_evento", parametros
    )

    assert condiciones == [
        "(timestamp_evento AT TIME ZONE :zona_horaria)::time >= :hora_inicio",
        "(timestamp_evento AT TIME ZONE :zona_horaria)::time <= :hora_fin",
    ]
    assert parametros["zona_horaria"] == "America/Guayaquil"


def test_sin_franja_horaria_no_se_anade_ninguna_condicion():
    parametros: dict = {}
    condiciones = VisualizacionTemporalRepository._condiciones_de_hora(
        SimpleNamespace(hora_inicio=None, hora_fin=None), "timestamp_medicion", parametros
    )

    assert condiciones == []
    assert parametros == {}


# ------------------------------------------------------------------------------ histograma


def medicion(sesion: str, inicio: datetime, segundo: int, node_id: int) -> Medicion:
    return Medicion(
        id_medicion=f"{sesion}-m{segundo}",
        sesion_id=sesion,
        sesion_nombre=f"Sesión {sesion}",
        report_index=segundo,
        timestamp_medicion=inicio + timedelta(seconds=segundo),
        cid=100,
        node_id=node_id,
        psc_pci=301,
        lac_tac=35191,
        tech="LTE",
        arfcn=850,
    )


class RepositorioHistograma:
    def __init__(self, mediciones):
        self.mediciones = sorted(mediciones, key=lambda m: m.timestamp_medicion)

    def existe_sesion(self, sesion_id):
        return any(m.sesion_id == sesion_id for m in self.mediciones)

    def obtener_mediciones_filtradas(self, filtros):
        return [m for m in self.mediciones if m.sesion_id in filtros.sesion_ids]


def _dos_sesiones_separadas_por_dias():
    """Sesión A de 10 min y sesión B de 4 min, cinco días después y empezando a media hora."""
    inicio_b = T0 + timedelta(days=5, minutes=30, seconds=17)
    mediciones = [
        medicion("a", T0, s, node_id=28100 + s // 120) for s in range(0, 600, 10)
    ] + [medicion("b", inicio_b, s, node_id=29100 + s // 60) for s in range(0, 240, 10)]
    return RepositorioHistograma(mediciones), inicio_b


def test_los_intervalos_en_minutos_empiezan_en_el_inicio_de_cada_sesion():
    repositorio, inicio_b = _dos_sesiones_separadas_por_dias()

    salida = obtener_celdas_repetidas(
        FiltrosTemporales(sesion_ids=["a", "b"]), minutos=3, repository=repositorio
    )

    assert salida.minutos == 3
    de_a = [b for b in salida.bins if b.sesion_id == "a"]
    de_b = [b for b in salida.bins if b.sesion_id == "b"]
    assert de_a[0].inicio == T0
    assert de_b[0].inicio == inicio_b
    assert de_b[0].sesion_nombre == "Sesión b"
    assert all(b.fin - b.inicio == timedelta(minutes=3) for b in salida.bins)
    # Orden cronológico: primero todos los intervalos de A, luego los de B.
    assert [b.sesion_id for b in salida.bins] == ["a"] * len(de_a) + ["b"] * len(de_b)


def test_el_tope_del_deslizador_es_la_duracion_de_la_sesion_mas_larga():
    repositorio, _ = _dos_sesiones_separadas_por_dias()

    salida = obtener_celdas_repetidas(FiltrosTemporales(sesion_ids=["a", "b"]), repository=repositorio)

    # A dura 9 min 50 s: se redondea hacia arriba. Los días entre sesiones no cuentan.
    assert salida.minutos_max == 10


def test_sin_minutos_se_analiza_el_total_de_todas_las_sesiones_juntas():
    repositorio, _ = _dos_sesiones_separadas_por_dias()

    salida = obtener_celdas_repetidas(FiltrosTemporales(sesion_ids=["a", "b"]), repository=repositorio)

    assert salida.minutos is None
    assert len(salida.bins) == 1
    assert salida.bins[0].sesion_id is None


def test_minutos_manda_sobre_el_intervalo_fijo():
    repositorio, _ = _dos_sesiones_separadas_por_dias()

    salida = obtener_celdas_repetidas(
        FiltrosTemporales(sesion_ids=["a"]), intervalo="5min", minutos=2, repository=repositorio
    )

    assert salida.minutos == 2
    assert all(b.fin - b.inicio == timedelta(minutes=2) for b in salida.bins)
