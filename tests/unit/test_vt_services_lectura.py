"""
Pruebas de los servicios de lectura del Módulo 2 (Fase 3, tarea 3.5).

Con **repositorio falso en memoria**: los servicios no conocen SQLAlchemy, así que se pueden
probar sin base de datos. Aquí se cubren los casos límite que las pruebas de integración no
pueden provocar cómodamente (huecos, ventanas en el borde, series vacías).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.modules.visualizacion_temporal.detector import Medicion
from app.modules.visualizacion_temporal.exceptions import (
    HandoverNoEncontrado,
    SesionNoEncontrada,
)
from app.modules.visualizacion_temporal.schemas import ParametroRF
from app.modules.visualizacion_temporal.services import (
    obtener_celdas_repetidas,
    obtener_resumen,
    obtener_series,
    obtener_tramos_celda,
    obtener_ventana_handover,
)

T0 = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
SESION = "s-1"


def medicion(segundo: int, *, node_id: int = 28100, **rf) -> Medicion:
    return Medicion(
        id_medicion=f"m{segundo}",
        sesion_id=SESION,
        sesion_nombre="SesionPrueba",
        report_index=segundo,
        timestamp_medicion=T0 + timedelta(seconds=segundo),
        cid=100,
        node_id=node_id,
        psc_pci=301,
        lac_tac=35191,
        tech="LTE",
        arfcn=850,
        **rf,
    )


class RepositorioFalso:
    def __init__(self, mediciones=None, eventos=None, cobertura=None):
        self.mediciones = mediciones or []
        self.eventos = eventos or []
        self.cobertura = cobertura or []

    def existe_sesion(self, sesion_id):
        return any(m.sesion_id == sesion_id for m in self.mediciones)

    def obtener_mediciones_filtradas(self, filtros):
        return [m for m in self.mediciones if m.sesion_id == filtros.sesion_id]

    def obtener_mediciones(self, sesion_id, desde=None, hasta=None):
        return [
            m
            for m in self.mediciones
            if m.sesion_id == sesion_id
            and (desde is None or m.timestamp_medicion >= desde)
            and (hasta is None or m.timestamp_medicion <= hasta)
        ]

    def obtener_mediciones_en_rango(self, sesion_id, t_inicio, t_fin):
        return self.obtener_mediciones(sesion_id, desde=t_inicio, hasta=t_fin)

    def obtener_cobertura_parametros(self, sesion_id):
        return self.cobertura

    def listar_handovers(self, filtros, page=1, page_size=50, orden="asc"):
        return len(self.eventos), self.eventos

    def obtener_handover(self, id_evento):
        return next((e for e in self.eventos if str(e["id_evento"]) == id_evento), None)


def filtros(sesion_id=SESION):
    return SimpleNamespace(
        sesion_id=sesion_id, desde=None, hasta=None, hora_inicio=None, hora_fin=None, tecnologia=[]
    )


# ================================================================================================
# Series
# ================================================================================================


def test_una_serie_pequena_no_se_muestrea():
    repo = RepositorioFalso([medicion(s, rsrp_dbm=-90 - s % 5) for s in range(50)])

    salida = obtener_series(filtros(), [ParametroRF.RSRP], max_puntos=3000, repository=repo)

    assert salida.downsampled is False
    assert salida.puntos_originales == 50
    assert salida.puntos_devueltos == 50


def test_una_serie_grande_se_muestrea_y_lo_declara():
    repo = RepositorioFalso([medicion(s, rsrp_dbm=-90 - (s % 20)) for s in range(5000)])

    salida = obtener_series(filtros(), [ParametroRF.RSRP], max_puntos=200, repository=repo)

    assert salida.downsampled is True
    assert salida.puntos_originales == 5000
    assert salida.puntos_devueltos <= 200


def test_un_hueco_de_captura_inserta_un_corte_en_la_linea():
    """Sin el corte, la gráfica dibujaría un segmento recto sobre un intervalo sin medidas."""
    mediciones = [medicion(s, rsrp_dbm=-90) for s in range(30)]
    mediciones += [medicion(s, rsrp_dbm=-95) for s in range(300, 330)]
    repo = RepositorioFalso(mediciones)

    salida = obtener_series(filtros(), [ParametroRF.RSRP], max_gap_s=30, repository=repo)

    assert salida.t.count(None) == 1
    assert salida.series["rsrp_dbm"].count(None) >= 1


def test_sin_hueco_no_se_corta_la_linea():
    repo = RepositorioFalso([medicion(s, rsrp_dbm=-90) for s in range(60)])

    salida = obtener_series(filtros(), [ParametroRF.RSRP], max_gap_s=30, repository=repo)

    assert None not in salida.t


def test_las_series_quedan_alineadas_con_el_eje_de_tiempos():
    repo = RepositorioFalso(
        [medicion(s, rsrp_dbm=-90, rsrq_db=-10) for s in range(500)]
    )

    salida = obtener_series(
        filtros(), [ParametroRF.RSRP, ParametroRF.RSRQ], max_puntos=100, repository=repo
    )

    for serie in salida.series.values():
        assert len(serie) == len(salida.t)


def test_un_parametro_sin_medidas_se_devuelve_lleno_de_nulos_y_se_declara():
    """Decisión D-5: la serie existe, pero la interfaz debe saber que está vacía."""
    repo = RepositorioFalso([medicion(s, rsrp_dbm=-90) for s in range(50)])

    salida = obtener_series(
        filtros(), [ParametroRF.RSRP, ParametroRF.RSSNR], repository=repo
    )

    assert all(v is None for v in salida.series["rssnr_db"])
    cobertura = {c.parametro: c for c in salida.cobertura}
    assert cobertura["rssnr_db"].disponible is False
    assert cobertura["rsrp_dbm"].disponible is True


def test_una_sesion_sin_mediciones_devuelve_series_vacias_sin_romper():
    repo = RepositorioFalso([medicion(0)])
    repo.obtener_mediciones_filtradas = lambda f: []

    salida = obtener_series(filtros(), [ParametroRF.RSRP], repository=repo)

    assert salida.t == []
    assert salida.puntos_originales == 0


def test_series_sobre_sesion_inexistente_lanza_error_de_dominio():
    repo = RepositorioFalso([medicion(0)])

    with pytest.raises(SesionNoEncontrada):
        obtener_series(filtros("otra"), [ParametroRF.RSRP], repository=repo)


# ================================================================================================
# Tramos de celda
# ================================================================================================


def test_los_tramos_agrupan_mediciones_consecutivas_de_la_misma_celda():
    mediciones = (
        [medicion(s, node_id=28100) for s in range(10)]
        + [medicion(s, node_id=28200) for s in range(10, 20)]
        + [medicion(s, node_id=28100) for s in range(20, 30)]
    )

    salida = obtener_tramos_celda(filtros(), repository=RepositorioFalso(mediciones))

    assert len(salida.tramos) == 3
    assert salida.celdas_distintas == 2


def test_la_altura_de_una_celda_es_estable_entre_tramos():
    """Es lo que permite comparar dos vistas de un vistazo."""
    mediciones = (
        [medicion(s, node_id=28100) for s in range(10)]
        + [medicion(s, node_id=28200) for s in range(10, 20)]
        + [medicion(s, node_id=28100) for s in range(20, 30)]
    )

    tramos = obtener_tramos_celda(filtros(), repository=RepositorioFalso(mediciones)).tramos

    assert tramos[0].valor_normalizado == tramos[2].valor_normalizado
    assert tramos[0].valor_normalizado != tramos[1].valor_normalizado


def test_con_una_sola_celda_la_altura_es_intermedia():
    repo = RepositorioFalso([medicion(s) for s in range(10)])

    tramos = obtener_tramos_celda(filtros(), repository=repo).tramos

    assert len(tramos) == 1
    assert tramos[0].valor_normalizado == 0.5


# ================================================================================================
# Ventana PRE / POST
# ================================================================================================


def evento_falso(segundo: int = 30) -> dict:
    return {
        "id_evento": "ev-1",
        "sesion_id": SESION,
        "sesion_nombre": "SesionPrueba",
        "timestamp_evento": T0 + timedelta(seconds=segundo),
        "report_index_evento": segundo,
        "celda_origen_clave": "LTE:1",
        "celda_destino_clave": "LTE:2",
        "tipo_evento": "intra_frecuencia",
        "ping_pong": False,
        "confianza": "alta",
        "duracion_permanencia_s": 29.0,
        "muestras_confirmacion": 2,
    }


def test_la_ventana_etiqueta_las_fases_correctamente():
    mediciones = [medicion(s, rsrp_dbm=-100 if s < 30 else -85) for s in range(60)]
    repo = RepositorioFalso(mediciones, eventos=[evento_falso(30)])

    salida = obtener_ventana_handover("ev-1", 5, 5, [ParametroRF.RSRP], repository=repo)

    assert salida.fase.count("evento") == 1
    assert salida.fase.count("pre") == 5
    assert salida.fase.count("post") == 5
    assert salida.t_relativo_s[0] == -5.0
    assert salida.t_relativo_s[-1] == 5.0


def test_las_estadisticas_comparan_antes_y_despues():
    mediciones = [medicion(s, rsrp_dbm=-100 if s < 30 else -85) for s in range(60)]
    repo = RepositorioFalso(mediciones, eventos=[evento_falso(30)])

    salida = obtener_ventana_handover("ev-1", 5, 5, [ParametroRF.RSRP], repository=repo)
    rsrp = salida.estadisticas["rsrp_dbm"]

    assert rsrp.media_pre == -100.0
    assert rsrp.media_post == -85.0
    assert rsrp.delta == 15.0
    assert rsrp.n_pre == 5 and rsrp.n_post == 6


def test_una_ventana_en_el_borde_del_dataset_no_rompe():
    """El primer handover puede no tener 5 s de datos por delante."""
    mediciones = [medicion(s, rsrp_dbm=-90) for s in range(10)]
    repo = RepositorioFalso(mediciones, eventos=[evento_falso(2)])

    salida = obtener_ventana_handover("ev-1", 5, 5, [ParametroRF.RSRP], repository=repo)

    assert salida.fase.count("pre") == 2  # solo hay 2 s antes del evento
    assert salida.estadisticas["rsrp_dbm"].n_pre == 2


def test_una_ventana_sin_medidas_de_un_parametro_no_inventa_delta():
    mediciones = [medicion(s, rsrp_dbm=-90) for s in range(60)]
    repo = RepositorioFalso(mediciones, eventos=[evento_falso(30)])

    salida = obtener_ventana_handover(
        "ev-1", 5, 5, [ParametroRF.RSRP, ParametroRF.RSSNR], repository=repo
    )
    sinr = salida.estadisticas["rssnr_db"]

    assert sinr.disponible is False
    assert sinr.delta is None
    assert sinr.media_pre is None and sinr.media_post is None


def test_ventana_de_handover_inexistente_lanza_error_de_dominio():
    repo = RepositorioFalso([medicion(0)], eventos=[])

    with pytest.raises(HandoverNoEncontrado):
        obtener_ventana_handover("no-existe", repository=repo)


# ================================================================================================
# Resumen y celdas repetidas
# ================================================================================================


def test_el_resumen_calcula_la_tasa_de_handovers_por_minuto():
    mediciones = [medicion(s, rsrp_dbm=-90) for s in range(121)]  # 120 s
    repo = RepositorioFalso(mediciones, eventos=[evento_falso(30), evento_falso(60)])

    salida = obtener_resumen(filtros(), repository=repo)

    assert salida.duracion_s == 120.0
    assert salida.tasa_ho_por_minuto == 1.0
    assert salida.total_handovers == 2


def test_el_resumen_de_una_sesion_sin_eventos_no_divide_por_cero():
    repo = RepositorioFalso([medicion(0, rsrp_dbm=-90)], eventos=[])

    salida = obtener_resumen(filtros(), repository=repo)

    assert salida.total_handovers == 0
    assert salida.tasa_ho_por_minuto is None


def test_las_celdas_repetidas_cuentan_una_visita_por_tramo():
    mediciones = (
        [medicion(s, node_id=28100) for s in range(10)]
        + [medicion(s, node_id=28200) for s in range(10, 20)]
        + [medicion(s, node_id=28100) for s in range(20, 30)]
    )

    salida = obtener_celdas_repetidas(filtros(), repository=RepositorioFalso(mediciones))
    celdas = {c.celda_clave: c for c in salida.bins[0].celdas}

    assert salida.total_celdas == 2
    assert max(c.n_visitas for c in celdas.values()) == 2


def test_el_parametro_top_limita_el_histograma():
    mediciones = [medicion(s, node_id=28100 + s) for s in range(20)]

    salida = obtener_celdas_repetidas(
        filtros(), top=5, repository=RepositorioFalso(mediciones)
    )

    assert len(salida.bins[0].celdas) == 5
    assert salida.total_celdas == 20
