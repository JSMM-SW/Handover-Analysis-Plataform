"""
Pruebas del análisis de varias sesiones a la vez.

El filtro admite una lista de sesiones. Lo que se protege aquí:

- que el contrato siga aceptando una sola sesión (compatibilidad);
- que las gráficas no unan el final de un recorrido con el principio de otro;
- que la misma celda en dos recorridos cuente como dos permanencias;
- que el resumen cuente las sesiones de verdad analizadas.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.visualizacion_temporal.detector import Medicion
from app.modules.visualizacion_temporal.exceptions import SesionNoEncontrada
from app.modules.visualizacion_temporal.schemas import FiltrosTemporales
from app.modules.visualizacion_temporal.services import (
    obtener_resumen,
    obtener_series,
    obtener_tramos_celda,
)

T0 = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


def medicion(sesion: str, segundo: int, *, node_id: int = 28100) -> Medicion:
    return Medicion(
        id_medicion=f"{sesion}-m{segundo}",
        sesion_id=sesion,
        sesion_nombre="Datos 1",  # mismo nombre en ambas: se cuentan por id, no por nombre
        report_index=segundo,
        timestamp_medicion=T0 + timedelta(seconds=segundo),
        cid=100,
        node_id=node_id,
        psc_pci=301,
        lac_tac=35191,
        tech="LTE",
        arfcn=850,
        rsrp_dbm=-90.0,
    )


class RepositorioMultisesion:
    """Repositorio en memoria que respeta la lista de sesiones del filtro."""

    def __init__(self, mediciones):
        self.mediciones = sorted(mediciones, key=lambda m: m.timestamp_medicion)

    def existe_sesion(self, sesion_id):
        return any(m.sesion_id == sesion_id for m in self.mediciones)

    def obtener_mediciones_filtradas(self, filtros):
        return [m for m in self.mediciones if m.sesion_id in filtros.sesion_ids]

    def obtener_cobertura_parametros(self, sesion_id):
        return []

    def listar_handovers(self, filtros, page=1, page_size=50, orden="asc"):
        return 0, []


# Dos recorridos consecutivos (sin hueco temporal entre ellos) sobre la misma celda.
MEDICIONES = [medicion("a", s) for s in range(10)] + [medicion("b", s) for s in range(10, 20)]


# ------------------------------------------------------------------------------ contrato


def test_el_filtro_sigue_aceptando_una_sola_sesion():
    filtros = FiltrosTemporales(sesion_id="a")

    assert filtros.sesion_ids == ["a"]
    assert filtros.sesion_id == "a"


def test_el_filtro_acepta_varias_sesiones_sin_duplicados():
    filtros = FiltrosTemporales(sesion_ids=["a", "b", "a"])

    assert filtros.sesion_ids == ["a", "b"]
    assert filtros.sesion_id == "a"


def test_el_filtro_exige_al_menos_una_sesion():
    with pytest.raises(ValueError, match="al menos una sesión"):
        FiltrosTemporales(sesion_ids=[])


# ------------------------------------------------------------------------------ servicios


def test_las_series_se_cortan_al_pasar_de_una_sesion_a_otra():
    repo = RepositorioMultisesion(MEDICIONES)

    series = obtener_series(FiltrosTemporales(sesion_ids=["a", "b"]), ["rsrp_dbm"], repository=repo)

    # 20 puntos + 1 corte nulo entre las dos sesiones, aunque no haya hueco temporal.
    assert series.t.count(None) == 1
    assert series.puntos_originales == 20


def test_la_misma_celda_en_dos_sesiones_son_dos_tramos():
    repo = RepositorioMultisesion(MEDICIONES)

    tramos = obtener_tramos_celda(FiltrosTemporales(sesion_ids=["a", "b"]), repository=repo)

    assert len(tramos.tramos) == 2
    assert tramos.celdas_distintas == 1


def test_el_resumen_cuenta_sesiones_por_id_aunque_compartan_nombre():
    repo = RepositorioMultisesion(MEDICIONES)

    resumen = obtener_resumen(FiltrosTemporales(sesion_ids=["a", "b"]), repository=repo)

    assert resumen.sesiones_analizadas == 2
    assert resumen.n_mediciones == 20


def test_si_una_de_las_sesiones_no_existe_se_avisa():
    repo = RepositorioMultisesion(MEDICIONES)

    with pytest.raises(SesionNoEncontrada):
        obtener_resumen(FiltrosTemporales(sesion_ids=["a", "no-existe"]), repository=repo)


def test_la_duracion_suma_cada_sesion_y_no_el_tiempo_entre_ellas():
    # Dos recorridos de 9 s separados por un mes: la duración analizada son 18 s, no un mes.
    lejana = [
        replace(m, timestamp_medicion=m.timestamp_medicion + timedelta(days=30))
        for m in (medicion("b", s) for s in range(10))
    ]
    repo = RepositorioMultisesion([medicion("a", s) for s in range(10)] + lejana)

    resumen = obtener_resumen(FiltrosTemporales(sesion_ids=["a", "b"]), repository=repo)

    assert resumen.duracion_s == 18
