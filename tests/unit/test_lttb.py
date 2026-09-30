"""Pruebas del downsampling LTTB (Fase 3, tarea 3.3)."""

import math

import pytest

from app.modules.visualizacion_temporal.lttb import (
    indice_de_mejor_cobertura,
    seleccionar_indices_lttb,
)


def serie_seno(n: int) -> tuple[list[float], list[float]]:
    xs = [float(i) for i in range(n)]
    ys = [math.sin(i / 10) * 20 - 90 for i in range(n)]
    return xs, ys


# ------------------------------------------------------------------------------------------------
# Garantías del contrato
# ------------------------------------------------------------------------------------------------


def test_conserva_el_primer_y_el_ultimo_punto():
    xs, ys = serie_seno(1000)

    indices = seleccionar_indices_lttb(xs, ys, 50)

    assert indices[0] == 0
    assert indices[-1] == 999


def test_nunca_devuelve_mas_de_max_puntos():
    xs, ys = serie_seno(5000)

    for max_puntos in (3, 10, 100, 1000, 4999):
        assert len(seleccionar_indices_lttb(xs, ys, max_puntos)) <= max_puntos


def test_los_indices_salen_ordenados_y_sin_repetir():
    xs, ys = serie_seno(2000)

    indices = seleccionar_indices_lttb(xs, ys, 137)

    assert indices == sorted(indices)
    assert len(indices) == len(set(indices))


def test_una_serie_que_ya_cabe_se_devuelve_entera():
    xs, ys = serie_seno(80)

    assert seleccionar_indices_lttb(xs, ys, 100) == list(range(80))
    assert seleccionar_indices_lttb(xs, ys, 80) == list(range(80))


def test_es_determinista():
    xs, ys = serie_seno(3000)

    assert seleccionar_indices_lttb(xs, ys, 200) == seleccionar_indices_lttb(xs, ys, 200)


def test_los_indices_son_validos_para_la_serie():
    xs, ys = serie_seno(1234)

    indices = seleccionar_indices_lttb(xs, ys, 97)

    assert all(0 <= i < 1234 for i in indices)


# ------------------------------------------------------------------------------------------------
# Calidad visual: lo que distingue LTTB de un muestreo ingenuo
# ------------------------------------------------------------------------------------------------


def test_conserva_un_pico_aislado_que_el_muestreo_uniforme_perderia():
    """El motivo de usar LTTB: un pico entre dos muestras uniformes desaparecería."""
    n = 1000
    xs = [float(i) for i in range(n)]
    ys = [-100.0] * n
    ys[437] = -40.0  # pico aislado, en una posición que el muestreo uniforme no visita

    indices = seleccionar_indices_lttb(xs, ys, 50)

    assert 437 in indices
    # Comprobación de contraste: el muestreo uniforme de 50 puntos sí lo pierde.
    uniformes = set(range(0, n, n // 50))
    assert 437 not in uniformes


def test_conserva_los_extremos_de_una_caida_brusca():
    """Una caída de señal antes de un handover debe seguir viéndose tras el muestreo."""
    n = 600
    xs = [float(i) for i in range(n)]
    ys = [-80.0] * 300 + [-115.0] * 300

    indices = seleccionar_indices_lttb(xs, ys, 40)
    valores = [ys[i] for i in indices]

    assert min(valores) == -115.0
    assert max(valores) == -80.0


# ------------------------------------------------------------------------------------------------
# Valores ausentes
# ------------------------------------------------------------------------------------------------


def test_funciona_con_valores_ausentes_intercalados():
    """Con datos reales, RSRQ solo tiene medida en el 16 % de las filas."""
    n = 1000
    xs = [float(i) for i in range(n)]
    ys = [(-90.0 + (i % 17)) if i % 5 == 0 else None for i in range(n)]

    indices = seleccionar_indices_lttb(xs, ys, 60)

    assert len(indices) <= 60
    assert indices[0] == 0 and indices[-1] == n - 1


def test_funciona_con_una_serie_entera_de_ausentes():
    """El caso de SINR en el dataset real: 0 % de cobertura y aun así hay que muestrear."""
    n = 500
    xs = [float(i) for i in range(n)]
    ys = [None] * n

    indices = seleccionar_indices_lttb(xs, ys, 30)

    assert len(indices) <= 30
    assert indices[0] == 0 and indices[-1] == n - 1


def test_funciona_si_la_serie_empieza_con_ausentes():
    n = 400
    xs = [float(i) for i in range(n)]
    ys = [None] * 100 + [-95.0 + (i % 11) for i in range(300)]

    indices = seleccionar_indices_lttb(xs, ys, 40)

    assert indices[0] == 0 and indices[-1] == n - 1


# ------------------------------------------------------------------------------------------------
# Casos límite
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("n", [0, 1, 2, 3])
def test_series_muy_cortas_no_rompen(n):
    xs = [float(i) for i in range(n)]
    ys = [-90.0] * n

    assert seleccionar_indices_lttb(xs, ys, 10) == list(range(n))


def test_max_puntos_uno_devuelve_solo_el_primero():
    xs, ys = serie_seno(100)

    assert seleccionar_indices_lttb(xs, ys, 1) == [0]


def test_max_puntos_dos_devuelve_los_extremos():
    xs, ys = serie_seno(100)

    assert seleccionar_indices_lttb(xs, ys, 2) == [0, 99]


def test_longitudes_distintas_lanzan_error():
    with pytest.raises(ValueError):
        seleccionar_indices_lttb([1.0, 2.0], [1.0], 10)


def test_max_puntos_invalido_lanza_error():
    xs, ys = serie_seno(100)

    with pytest.raises(ValueError):
        seleccionar_indices_lttb(xs, ys, 0)


# ------------------------------------------------------------------------------------------------
# Elección de la serie de referencia
# ------------------------------------------------------------------------------------------------


def test_se_elige_como_referencia_la_serie_con_mas_medidas():
    series = {
        "rsrp_dbm": [-90.0, -91.0, -92.0, -93.0],
        "rsrq_db": [-10.0, None, None, None],
        "rssnr_db": [None, None, None, None],
    }

    assert indice_de_mejor_cobertura(series) == "rsrp_dbm"


def test_la_referencia_es_estable_ante_empates():
    """Con la misma cobertura se desempata por nombre: el muestreo no puede ser aleatorio."""
    series = {"rsrq_db": [-10.0, -11.0], "rsrp_dbm": [-90.0, -91.0]}

    assert indice_de_mejor_cobertura(series) == "rsrp_dbm"
    assert indice_de_mejor_cobertura(series) == indice_de_mejor_cobertura(series)


def test_sin_series_no_hay_referencia():
    assert indice_de_mejor_cobertura({}) is None
