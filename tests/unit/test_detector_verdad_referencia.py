"""
Validación del detector contra la verdad de referencia (tarea 2.6 de la Fase 2).

El dataset sintético de `tests/fixtures/dataset_sintetico.py` declara **a mano** dónde están sus
handovers. Aquí se comprueba que el algoritmo los redescubre exactamente.

> Regla del enunciado: si el número o los instantes no coinciden, **el algoritmo está mal, no los
> datos.** Estas pruebas son el criterio de aceptación de HU-C2-001.
"""

from datetime import timedelta

import pytest

from app.modules.visualizacion_temporal.detector import (
    Medicion,
    detectar_handovers_detallado,
)
from tests.fixtures.dataset_sintetico import (
    EVENTOS_ESPERADOS,
    INICIO_UTC,
    MAX_GAP_S,
    MUESTRAS_CONFIRMACION,
    SESION_ID,
    TOTAL_HANDOVERS_ESPERADOS,
    VENTANA_PING_PONG_S,
    celda_por_etiqueta,
    generar_mediciones,
)

_CAMPOS_MEDICION = set(Medicion.__dataclass_fields__)


def _a_mediciones() -> list[Medicion]:
    """Traduce las filas del fixture al contrato que consume el detector."""
    return [
        Medicion(
            id_medicion=f"sint-{fila['report_index']}",
            **{k: v for k, v in fila.items() if k in _CAMPOS_MEDICION and k != "id_medicion"},
        )
        for fila in generar_mediciones()
    ]


@pytest.fixture(scope="module")
def resultado():
    return detectar_handovers_detallado(
        _a_mediciones(),
        muestras_confirmacion=MUESTRAS_CONFIRMACION,
        ventana_ping_pong_s=VENTANA_PING_PONG_S,
        max_gap_s=MAX_GAP_S,
    )


def _segundo(evento) -> int:
    return int((evento.timestamp_evento - INICIO_UTC).total_seconds())


# ------------------------------------------------------------------------------------------------
# CA1 y CA3 de HU-C2-001
# ------------------------------------------------------------------------------------------------


def test_detecta_exactamente_los_handovers_declarados(resultado):
    """CA3 — el total coincide con la verdad de referencia."""
    assert len(resultado.eventos) == TOTAL_HANDOVERS_ESPERADOS


def test_los_instantes_coinciden_con_la_verdad_de_referencia(resultado):
    """CA1 — no solo cuántos: exactamente en qué segundo ocurre cada uno."""
    detectados = [_segundo(e) for e in resultado.eventos]
    esperados = [e.segundo for e in EVENTOS_ESPERADOS]

    assert detectados == esperados


def test_cada_evento_registra_celda_origen_y_destino_correctas(resultado):
    """CA2 — fecha, hora, celda origen y celda destino."""
    for detectado, esperado in zip(resultado.eventos, EVENTOS_ESPERADOS):
        origen = celda_por_etiqueta(esperado.origen)
        destino = celda_por_etiqueta(esperado.destino)

        assert detectado.celda_origen_clave == origen.clave
        assert detectado.celda_destino_clave == destino.clave
        assert detectado.timestamp_evento == INICIO_UTC + timedelta(seconds=esperado.segundo)


def test_la_clasificacion_de_cada_evento_es_la_declarada(resultado):
    detectados = [e.tipo_evento for e in resultado.eventos]
    esperados = [e.tipo_evento for e in EVENTOS_ESPERADOS]

    assert detectados == esperados


def test_el_ping_pong_se_marca_donde_toca(resultado):
    detectados = [e.ping_pong for e in resultado.eventos]
    esperados = [e.ping_pong for e in EVENTOS_ESPERADOS]

    assert detectados == esperados
    assert sum(detectados) == 1


def test_la_confianza_de_cada_evento_es_la_declarada(resultado):
    detectados = [e.confianza for e in resultado.eventos]
    esperados = [e.confianza for e in EVENTOS_ESPERADOS]

    assert detectados == esperados


# ------------------------------------------------------------------------------------------------
# Casos que el dataset incluye a propósito
# ------------------------------------------------------------------------------------------------


def test_el_hueco_de_captura_no_genera_ningun_evento(resultado):
    """30 s sin datos con la misma celda a ambos lados: no es un handover."""
    assert resultado.diagnostico.cambios_descartados_por_hueco == 0
    assert not any(432 <= _segundo(e) < 462 for e in resultado.eventos)


def test_hay_dos_eventos_inter_rat(resultado):
    inter_rat = [e for e in resultado.eventos if e.tipo_evento == "inter_rat"]

    assert len(inter_rat) == 2
    assert inter_rat[0].tipo_tecnologia == "LTE->WCDMA"
    assert inter_rat[1].tipo_tecnologia == "WCDMA->LTE"


def test_ninguna_medicion_queda_sin_identidad(resultado):
    assert resultado.diagnostico.mediciones_sin_identidad == 0
    assert resultado.diagnostico.mediciones_recibidas == 600
    assert resultado.diagnostico.sesiones_analizadas == 1


def test_todos_los_eventos_pertenecen_a_la_sesion_sintetica(resultado):
    assert {e.sesion_id for e in resultado.eventos} == {SESION_ID}


def test_la_señal_mejora_tras_cada_handover_entre_celdas_lte(resultado):
    """El dataset degrada la señal antes del HO y la recupera después: delta positivo."""
    for evento in resultado.eventos:
        if evento.delta_rsrp_db is not None:
            assert evento.delta_rsrp_db > 0, (
                f"El HO del segundo {_segundo(evento)} no mejora el RSRP"
            )


def test_el_delta_de_sinr_existe_solo_donde_hay_medida(resultado):
    """RSSNR está a propósito solo en la primera mitad del recorrido."""
    con_delta = [e for e in resultado.eventos if e.delta_rssnr_db is not None]
    sin_delta = [e for e in resultado.eventos if e.delta_rssnr_db is None]

    assert con_delta, "Falta el caso con medida de SINR"
    assert sin_delta, "Falta el caso sin medida de SINR"
    assert all(_segundo(e) < 270 for e in con_delta)


# ------------------------------------------------------------------------------------------------
# Sensibilidad a los parámetros
# ------------------------------------------------------------------------------------------------


def test_una_confirmacion_mas_exigente_descarta_el_ping_pong():
    """Los tramos del ping-pong duran 6 s: con confirmación de 7 muestras desaparecen."""
    resultado = detectar_handovers_detallado(_a_mediciones(), muestras_confirmacion=7)

    assert len(resultado.eventos) < TOTAL_HANDOVERS_ESPERADOS
    assert not any(e.ping_pong for e in resultado.eventos)


def test_un_max_gap_menor_que_el_hueco_no_cambia_nada_porque_la_celda_es_la_misma():
    """El hueco del dataset tiene la misma celda a ambos lados: max_gap es irrelevante ahí."""
    estricto = detectar_handovers_detallado(_a_mediciones(), max_gap_s=5)

    assert len(estricto.eventos) == TOTAL_HANDOVERS_ESPERADOS
    assert estricto.diagnostico.cambios_descartados_por_hueco == 0


def test_la_deteccion_sobre_el_dataset_es_reproducible():
    primera = detectar_handovers_detallado(_a_mediciones()).eventos
    segunda = detectar_handovers_detallado(_a_mediciones()).eventos

    assert primera == segunda
