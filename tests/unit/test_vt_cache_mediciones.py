"""
Pruebas de la caché de mediciones y del filtrado en memoria del repositorio.

Las mediciones de cada sesión se descargan una sola vez y los filtros se aplican sobre ellas
(`filtrar_mediciones`), que es la réplica del `WHERE` que antes llevaba la consulta. Estas pruebas
fijan esa equivalencia y las garantías de la caché. No necesitan base de datos.
"""

import threading
import time as reloj
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.modules.visualizacion_temporal import repository
from app.modules.visualizacion_temporal.detector import Medicion
from app.modules.visualizacion_temporal.repository import (
    _CacheMediciones,
    _orden_temporal,
    filtrar_mediciones,
)

UTC = timezone.utc
#: 21:00 UTC son las 16:00 en Ecuador (UTC−5, sin horario de verano).
INICIO = datetime(2026, 9, 28, 21, 0, 0, tzinfo=UTC)


def medicion(segundo: int, tech: str | None = "LTE", report_index: int | None = None) -> Medicion:
    return Medicion(
        id_medicion=f"m{segundo}-{report_index}",
        sesion_id="s1",
        timestamp_medicion=INICIO + timedelta(seconds=segundo),
        cid=1,
        tech=tech,
        report_index=report_index,
    )


def filtros(**valores) -> SimpleNamespace:
    base = dict(
        desde=None, hasta=None, hora_inicio=None, hora_fin=None, tecnologia=[], zona_horaria="UTC"
    )
    return SimpleNamespace(**{**base, **valores})


# ------------------------------------------------------------------------------------------------
# Filtrado en memoria
# ------------------------------------------------------------------------------------------------


def test_sin_filtros_devuelve_una_copia_para_no_tocar_la_cache():
    mediciones = [medicion(0), medicion(1)]

    resultado = filtrar_mediciones(mediciones, filtros())
    resultado.clear()

    assert len(mediciones) == 2


def test_desde_y_hasta_incluyen_los_extremos():
    mediciones = [medicion(s) for s in range(5)]

    resultado = filtrar_mediciones(
        mediciones,
        filtros(desde=INICIO + timedelta(seconds=1), hasta=INICIO + timedelta(seconds=3)),
    )

    assert [m.id_medicion for m in resultado] == ["m1-None", "m2-None", "m3-None"]


def test_una_fecha_sin_zona_se_toma_en_utc_como_hace_supabase():
    mediciones = [medicion(0), medicion(60)]

    resultado = filtrar_mediciones(mediciones, filtros(desde=datetime(2026, 9, 28, 21, 1, 0)))

    assert [m.id_medicion for m in resultado] == ["m60-None"]


def test_la_franja_horaria_se_compara_en_la_zona_del_usuario():
    """16:00-16:30 en Ecuador son 21:00-21:30 UTC: en UTC la franja no encontraría nada."""
    mediciones = [medicion(0), medicion(20 * 60), medicion(40 * 60)]

    en_ecuador = filtrar_mediciones(
        mediciones,
        filtros(hora_inicio=time(16, 0), hora_fin=time(16, 30), zona_horaria="America/Guayaquil"),
    )
    en_utc = filtrar_mediciones(
        mediciones, filtros(hora_inicio=time(16, 0), hora_fin=time(16, 30), zona_horaria="UTC")
    )

    assert [m.id_medicion for m in en_ecuador] == ["m0-None", "m1200-None"]
    assert en_utc == []


def test_la_franja_horaria_se_aplica_a_cada_dia():
    otro_dia = Medicion(
        id_medicion="otro-dia",
        sesion_id="s1",
        timestamp_medicion=INICIO + timedelta(days=1, minutes=10),
        cid=1,
        tech="LTE",
    )

    resultado = filtrar_mediciones(
        [medicion(0), otro_dia],
        filtros(hora_inicio=time(16, 0), hora_fin=time(16, 30), zona_horaria="America/Guayaquil"),
    )

    assert len(resultado) == 2


def test_el_filtro_de_tecnologia_no_deja_pasar_mediciones_sin_tecnologia():
    mediciones = [medicion(0, "LTE"), medicion(1, "WCDMA"), medicion(2, None)]

    resultado = filtrar_mediciones(mediciones, filtros(tecnologia=["WCDMA"]))

    assert [m.tech for m in resultado] == ["WCDMA"]


def test_varias_sesiones_se_ordenan_como_order_by_con_nulls_last():
    sin_indice = medicion(0, report_index=None)
    con_indice = medicion(0, report_index=7)
    posterior = medicion(1, report_index=0)

    assert sorted([posterior, sin_indice, con_indice], key=_orden_temporal) == [
        con_indice,
        sin_indice,
        posterior,
    ]


# ------------------------------------------------------------------------------------------------
# Caché de sesiones
# ------------------------------------------------------------------------------------------------


class Base:
    """Base de datos de juguete: cuenta lecturas y permite cambiar la huella de una sesión."""

    def __init__(self, filas_por_sesion: dict[str, int], retardo_s: float = 0.0):
        self.filas = dict(filas_por_sesion)
        self.version = {s: 1 for s in filas_por_sesion}
        self.retardo_s = retardo_s
        self.huellas_leidas = 0
        self.descargas = 0

    def huella(self, sesion_id):
        self.huellas_leidas += 1
        return self.filas.get(sesion_id, 0), self.version.get(sesion_id)

    def mediciones(self, sesion_id):
        self.descargas += 1
        reloj.sleep(self.retardo_s)
        return [medicion(s) for s in range(self.filas[sesion_id])]

    def leer(self, cache, sesion_id):
        return cache.obtener(
            sesion_id,
            leer_huella=lambda: self.huella(sesion_id),
            leer_mediciones=lambda: self.mediciones(sesion_id),
        )


def test_peticiones_simultaneas_comparten_una_sola_descarga():
    base = Base({"s1": 3}, retardo_s=0.2)
    cache = _CacheMediciones(max_mediciones=100, segundos_confianza=60)
    resultados = []

    hilos = [
        threading.Thread(target=lambda: resultados.append(base.leer(cache, "s1")))
        for _ in range(6)
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert base.descargas == 1
    assert base.huellas_leidas == 1
    assert all(len(r) == 3 for r in resultados)


def test_dentro_de_la_ventana_de_confianza_no_se_vuelve_a_mirar_la_base():
    base = Base({"s1": 3})
    cache = _CacheMediciones(max_mediciones=100, segundos_confianza=60)

    base.leer(cache, "s1")
    base.leer(cache, "s1")

    assert base.huellas_leidas == 1
    assert base.descargas == 1


def test_pasada_la_ventana_se_comprueba_la_huella_y_si_coincide_no_se_descarga():
    base = Base({"s1": 3})
    cache = _CacheMediciones(max_mediciones=100, segundos_confianza=0)

    base.leer(cache, "s1")
    base.leer(cache, "s1")

    assert base.huellas_leidas == 2
    assert base.descargas == 1


@pytest.mark.parametrize("cambio", ["filas", "version"])
def test_si_el_etl_cambia_la_sesion_se_vuelve_a_descargar(cambio):
    base = Base({"s1": 3})
    cache = _CacheMediciones(max_mediciones=100, segundos_confianza=0)
    base.leer(cache, "s1")

    if cambio == "filas":
        base.filas["s1"] = 5
    else:
        base.version["s1"] = 2  # el Módulo 1 corrigió alguna fila (nuevo xmin)

    assert len(base.leer(cache, "s1")) == base.filas["s1"]
    assert base.descargas == 2


def test_una_sesion_sin_filas_no_se_descarga_ni_se_guarda():
    base = Base({"s1": 3})
    cache = _CacheMediciones(max_mediciones=100, segundos_confianza=0)
    base.leer(cache, "s1")

    base.filas["s1"] = 0  # el Módulo 1 borró la sesión

    assert base.leer(cache, "s1") == []
    assert base.descargas == 1


def test_al_pasar_el_limite_se_descartan_las_sesiones_usadas_hace_mas_tiempo():
    base = Base({"s1": 4, "s2": 4, "s3": 4})
    cache = _CacheMediciones(max_mediciones=8, segundos_confianza=60)

    base.leer(cache, "s1")
    base.leer(cache, "s2")
    base.leer(cache, "s1")  # s1 pasa a ser la más reciente
    base.leer(cache, "s3")  # no caben las tres: sale s2
    descargas = base.descargas

    base.leer(cache, "s1")
    base.leer(cache, "s3")
    assert base.descargas == descargas

    base.leer(cache, "s2")
    assert base.descargas == descargas + 1


def test_la_ultima_sesion_se_queda_aunque_sola_supere_el_limite():
    base = Base({"grande": 10})
    cache = _CacheMediciones(max_mediciones=5, segundos_confianza=60)

    base.leer(cache, "grande")
    base.leer(cache, "grande")

    assert base.descargas == 1


def test_si_la_descarga_falla_no_se_guarda_nada_y_la_siguiente_reintenta():
    base = Base({"s1": 3})
    cache = _CacheMediciones(max_mediciones=100, segundos_confianza=60)

    def fallar():
        raise ConnectionError("se cayó la conexión")

    with pytest.raises(ConnectionError):
        cache.obtener("s1", leer_huella=lambda: base.huella("s1"), leer_mediciones=fallar)

    assert len(base.leer(cache, "s1")) == 3


def test_invalidar_el_esquema_olvida_tambien_las_mediciones(monkeypatch):
    base = Base({"s1": 3})
    cache = _CacheMediciones(max_mediciones=100, segundos_confianza=60)
    monkeypatch.setattr(repository, "_cache_mediciones", cache)
    base.leer(cache, "s1")

    repository.invalidar_cache_esquema()
    base.leer(cache, "s1")

    assert base.descargas == 2
