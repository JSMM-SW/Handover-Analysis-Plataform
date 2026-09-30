"""
Pruebas unitarias del detector de handovers (Fase 2, HU-C2-001).

Los fixtures se construyen dentro de cada prueba: el detector es puro y no necesita base de datos.
La última sección lo contrasta contra la **verdad de referencia** del dataset sintético de la
Fase 1, que declara a mano dónde están los handovers.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.visualizacion_temporal.detector import (
    CONFIANZA_ALTA,
    CONFIANZA_BAJA,
    TIPO_DESCONOCIDO,
    TIPO_INTER_FRECUENCIA,
    TIPO_INTER_RAT,
    TIPO_INTRA_FRECUENCIA,
    Medicion,
    clave_de_celda,
    confianza_de_celda,
    detectar_handovers,
    detectar_handovers_detallado,
)

T0 = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
SESION = "sesion-1"


def medicion(
    segundo: int,
    *,
    cid: int = 100,
    node_id: int | None = 28000,
    tech: str = "LTE",
    arfcn: int | None = 850,
    psc_pci: int | None = 300,
    lac_tac: int | None = 35191,
    sesion_id: str = SESION,
    **rf,
) -> Medicion:
    """Construye una medición sintética. Los parámetros RF se pasan por nombre."""
    return Medicion(
        id_medicion=f"m-{sesion_id}-{segundo}",
        sesion_id=sesion_id,
        sesion_nombre="SesionPrueba",
        report_index=segundo,
        timestamp_medicion=T0 + timedelta(seconds=segundo),
        cid=cid,
        node_id=node_id,
        psc_pci=psc_pci,
        lac_tac=lac_tac,
        tech=tech,
        arfcn=arfcn,
        **rf,
    )


def serie(desde: int, hasta: int, **kwargs) -> list[Medicion]:
    """Mediciones a 1 Hz en `[desde, hasta)` con la misma celda."""
    return [medicion(s, **kwargs) for s in range(desde, hasta)]


# ================================================================================================
# Identidad de celda
# ================================================================================================


def test_identidad_lte_usa_el_eci_no_el_cid():
    """En LTE el cid es el sector; la identidad es node_id*256+cid (docs/06 §3.1)."""
    assert clave_de_celda(medicion(0, node_id=28178, cid=198)) == f"LTE:{28178 * 256 + 198}"


def test_dos_celdas_con_el_mismo_cid_y_distinto_nodo_son_distintas():
    """Es el caso real que hace insuficiente el cid: 9 de 26 cid se repiten entre nodos."""
    a = clave_de_celda(medicion(0, node_id=28178, cid=191))
    b = clave_de_celda(medicion(0, node_id=28868, cid=191))
    assert a != b


def test_identidad_sin_node_id_cae_a_la_forma_de_reserva():
    clave = clave_de_celda(medicion(0, tech="LTE", node_id=None, cid=191, lac_tac=33184))
    assert clave == "LTE:33184:191"


def test_identidad_en_wcdma_no_usa_eci():
    clave = clave_de_celda(medicion(0, tech="WCDMA", node_id=None, cid=30405, lac_tac=13163))
    assert clave == "WCDMA:13163:30405"


def test_sin_cid_no_hay_identidad():
    assert clave_de_celda(medicion(0, cid=None)) is None


def test_confianza_baja_sin_node_id_en_lte():
    assert confianza_de_celda(medicion(0, tech="LTE", node_id=None)) == CONFIANZA_BAJA
    assert confianza_de_celda(medicion(0, tech="LTE", node_id=28000)) == CONFIANZA_ALTA
    # En WCDMA no existe node_id: su ausencia no degrada la confianza.
    assert confianza_de_celda(medicion(0, tech="WCDMA", node_id=None)) == CONFIANZA_ALTA


# ================================================================================================
# Escenarios del enunciado de la Fase 2
# ================================================================================================


def test_serie_sin_cambios_de_celda_no_produce_eventos():
    assert detectar_handovers(serie(0, 60)) == []


def test_un_cambio_limpio_produce_un_handover_con_origen_y_destino_correctos():
    mediciones = serie(0, 30, node_id=28100) + serie(30, 60, node_id=28200)

    eventos = detectar_handovers(mediciones)

    assert len(eventos) == 1
    evento = eventos[0]
    assert evento.celda_origen_clave == f"LTE:{28100 * 256 + 100}"
    assert evento.celda_destino_clave == f"LTE:{28200 * 256 + 100}"
    assert evento.timestamp_evento == T0 + timedelta(seconds=30)
    assert evento.medicion_previa_id == "m-sesion-1-29"
    assert evento.medicion_posterior_id == "m-sesion-1-30"


def test_muestra_espuria_que_vuelve_atras_se_filtra_por_confirmacion():
    """A…A B A…A con una sola muestra de B: ruido de medición, no handover."""
    mediciones = serie(0, 30, node_id=28100) + [medicion(30, node_id=28200)] + serie(31, 60, node_id=28100)

    resultado = detectar_handovers_detallado(mediciones, muestras_confirmacion=2)

    assert resultado.eventos == []
    assert resultado.diagnostico.tramos_no_confirmados == 1


def test_con_confirmacion_de_una_muestra_la_espuria_si_se_registra():
    """El parámetro funciona: con muestras_confirmacion=1 nada se filtra.

    Nota: la secuencia A→B→A produce **dos** eventos (A→B y B→A), no uno. El enunciado de la
    fase decía "1 handover"; es impreciso, porque volver a A es en sí mismo un cambio de celda.
    """
    mediciones = serie(0, 30, node_id=28100) + [medicion(30, node_id=28200)] + serie(31, 60, node_id=28100)

    eventos = detectar_handovers(mediciones, muestras_confirmacion=1)

    assert len(eventos) == 2
    assert eventos[0].celda_destino_clave == f"LTE:{28200 * 256 + 100}"
    assert eventos[1].celda_destino_clave == f"LTE:{28100 * 256 + 100}"


def test_una_muestra_espuria_al_final_de_la_serie_tambien_se_filtra():
    mediciones = serie(0, 30, node_id=28100) + [medicion(30, node_id=28200)]

    assert detectar_handovers(mediciones, muestras_confirmacion=2) == []
    assert len(detectar_handovers(mediciones, muestras_confirmacion=1)) == 1


def test_secuencia_ping_pong_marca_el_segundo_evento():
    """A→B→A en 6 s: el segundo evento vuelve a la celda de origen del primero."""
    mediciones = serie(0, 30, node_id=28100) + serie(30, 33, node_id=28200) + serie(33, 60, node_id=28100)

    eventos = detectar_handovers(mediciones, muestras_confirmacion=2, ventana_ping_pong_s=10)

    assert len(eventos) == 2
    assert eventos[0].ping_pong is False
    assert eventos[1].ping_pong is True


def test_la_vuelta_tardia_no_es_ping_pong():
    """Si la vuelta ocurre fuera de la ventana, es movilidad normal, no ping-pong."""
    mediciones = serie(0, 30, node_id=28100) + serie(30, 60, node_id=28200) + serie(60, 90, node_id=28100)

    eventos = detectar_handovers(mediciones, ventana_ping_pong_s=10)

    assert len(eventos) == 2
    assert eventos[1].ping_pong is False


def test_cambio_de_tecnologia_es_inter_rat():
    mediciones = serie(0, 30, tech="LTE", node_id=28100, arfcn=850) + serie(
        30, 60, tech="WCDMA", node_id=None, cid=30405, lac_tac=13163, arfcn=None
    )

    eventos = detectar_handovers(mediciones)

    assert len(eventos) == 1
    assert eventos[0].tipo_evento == TIPO_INTER_RAT
    assert eventos[0].tipo_tecnologia == "LTE->WCDMA"


def test_mismo_arfcn_es_intra_frecuencia_y_distinto_es_inter_frecuencia():
    intra = serie(0, 30, node_id=28100, arfcn=850) + serie(30, 60, node_id=28200, arfcn=850)
    inter = serie(0, 30, node_id=28100, arfcn=850) + serie(30, 60, node_id=28200, arfcn=9435)

    assert detectar_handovers(intra)[0].tipo_evento == TIPO_INTRA_FRECUENCIA
    assert detectar_handovers(inter)[0].tipo_evento == TIPO_INTER_FRECUENCIA


def test_sin_arfcn_el_tipo_es_desconocido():
    """El arfcn es centinela en el 82,8 % de las filas reales: hay que preverlo."""
    mediciones = serie(0, 30, node_id=28100, arfcn=None) + serie(30, 60, node_id=28200, arfcn=None)

    assert detectar_handovers(mediciones)[0].tipo_evento == TIPO_DESCONOCIDO


def test_hueco_largo_entre_celdas_distintas_no_registra_evento():
    """Un salto de captura no es movilidad observada."""
    mediciones = serie(0, 30, node_id=28100) + serie(90, 120, node_id=28200)

    resultado = detectar_handovers_detallado(mediciones, max_gap_s=30)

    assert resultado.eventos == []
    assert resultado.diagnostico.cambios_descartados_por_hueco == 1


def test_el_mismo_hueco_con_max_gap_amplio_si_registra_evento():
    mediciones = serie(0, 30, node_id=28100) + serie(90, 120, node_id=28200)

    assert len(detectar_handovers(mediciones, max_gap_s=120)) == 1


def test_hueco_largo_con_la_misma_celda_no_produce_nada():
    """El caso del dataset real: 30 s sin captura y la misma celda a ambos lados."""
    mediciones = serie(0, 30, node_id=28100) + serie(90, 120, node_id=28100)

    resultado = detectar_handovers_detallado(mediciones, max_gap_s=30)

    assert resultado.eventos == []
    assert resultado.diagnostico.cambios_descartados_por_hueco == 0


def test_identidad_incompleta_degrada_la_confianza_del_evento():
    mediciones = serie(0, 30, node_id=28100) + serie(
        30, 60, node_id=None, cid=191, lac_tac=33184
    )

    evento = detectar_handovers(mediciones)[0]

    assert evento.confianza == CONFIANZA_BAJA
    assert evento.celda_destino_clave == "LTE:33184:191"


def test_las_mediciones_sin_cid_se_descartan_sin_romper_la_deteccion():
    mediciones = (
        serie(0, 30, node_id=28100)
        + [medicion(30, cid=None), medicion(31, cid=None)]
        + serie(32, 60, node_id=28200)
    )

    resultado = detectar_handovers_detallado(mediciones)

    assert resultado.diagnostico.mediciones_sin_identidad == 2
    assert len(resultado.eventos) == 1


# ================================================================================================
# Deltas de radiofrecuencia
# ================================================================================================


def test_los_deltas_se_calculan_entre_las_mediciones_que_acotan_el_evento():
    mediciones = serie(0, 30, node_id=28100, rsrp_dbm=-100, rsrq_db=-15, rssnr_db=3) + serie(
        30, 60, node_id=28200, rsrp_dbm=-85, rsrq_db=-9, rssnr_db=12
    )

    evento = detectar_handovers(mediciones)[0]

    assert evento.delta_rsrp_db == pytest.approx(15.0)
    assert evento.delta_rsrq_db == pytest.approx(6.0)
    assert evento.delta_rssnr_db == pytest.approx(9.0)


def test_un_delta_con_un_extremo_ausente_es_none_nunca_cero():
    """`None` = no se pudo medir. `0.0` = no cambió. Son cosas distintas (decisión D-5)."""
    mediciones = serie(0, 30, node_id=28100, rsrp_dbm=-100, rssnr_db=None) + serie(
        30, 60, node_id=28200, rsrp_dbm=-100, rssnr_db=12
    )

    evento = detectar_handovers(mediciones)[0]

    assert evento.delta_rssnr_db is None
    assert evento.delta_rsrp_db == 0.0  # medido y sin cambio: no es lo mismo que None


def test_rssnr_ausente_en_toda_la_serie_no_impide_la_deteccion():
    """El caso del dataset real: SINR con 0 % de disponibilidad."""
    mediciones = serie(0, 30, node_id=28100, rsrp_dbm=-95) + serie(30, 60, node_id=28200, rsrp_dbm=-88)

    evento = detectar_handovers(mediciones)[0]

    assert evento.delta_rssnr_db is None
    assert evento.delta_rsrp_db == pytest.approx(7.0)


def test_duracion_de_permanencia_en_la_celda_origen():
    mediciones = serie(0, 41, node_id=28100) + serie(41, 60, node_id=28200)

    evento = detectar_handovers(mediciones)[0]

    assert evento.duracion_permanencia_s == pytest.approx(40.0)


# ================================================================================================
# Robustez
# ================================================================================================


def test_lista_vacia_no_lanza_excepcion():
    assert detectar_handovers([]) == []


def test_una_sola_medicion_no_produce_eventos():
    assert detectar_handovers([medicion(0)]) == []


def test_las_mediciones_desordenadas_se_ordenan_antes_de_detectar():
    mediciones = serie(0, 30, node_id=28100) + serie(30, 60, node_id=28200)
    desordenadas = list(reversed(mediciones))

    assert len(detectar_handovers(desordenadas)) == 1


def test_el_desempate_usa_report_index_cuando_el_timestamp_se_repite():
    """A 1 Hz la app puede emitir dos filas en el mismo segundo (BLQ-08)."""
    base = serie(0, 30, node_id=28100)
    # Dos mediciones en el mismo segundo, en orden de entrada invertido.
    empatadas = [
        Medicion(
            id_medicion="tardia",
            sesion_id=SESION,
            timestamp_medicion=T0 + timedelta(seconds=30),
            report_index=31,
            cid=100,
            node_id=28200,
            tech="LTE",
            arfcn=850,
        ),
        Medicion(
            id_medicion="temprana",
            sesion_id=SESION,
            timestamp_medicion=T0 + timedelta(seconds=30),
            report_index=30,
            cid=100,
            node_id=28200,
            tech="LTE",
            arfcn=850,
        ),
    ]

    evento = detectar_handovers(base + empatadas)[0]

    assert evento.medicion_posterior_id == "temprana"


def test_nunca_se_detecta_un_handover_entre_sesiones_distintas():
    """Cada sesión es un recorrido independiente (docs/06 §6.3)."""
    mediciones = serie(0, 30, node_id=28100, sesion_id="A") + serie(
        30, 60, node_id=28200, sesion_id="B"
    )

    resultado = detectar_handovers_detallado(mediciones)

    assert resultado.eventos == []
    assert resultado.diagnostico.sesiones_analizadas == 2


def test_dos_sesiones_con_handovers_propios_se_detectan_por_separado():
    mediciones = (
        serie(0, 30, node_id=28100, sesion_id="A")
        + serie(30, 60, node_id=28200, sesion_id="A")
        + serie(0, 30, node_id=28300, sesion_id="B")
        + serie(30, 60, node_id=28400, sesion_id="B")
    )

    eventos = detectar_handovers(mediciones)

    assert len(eventos) == 2
    assert {e.sesion_id for e in eventos} == {"A", "B"}


@pytest.mark.parametrize("muestras", [0, -1])
def test_muestras_confirmacion_invalida_lanza_error(muestras):
    with pytest.raises(ValueError):
        detectar_handovers(serie(0, 10), muestras_confirmacion=muestras)


def test_max_gap_invalido_lanza_error():
    with pytest.raises(ValueError):
        detectar_handovers(serie(0, 10), max_gap_s=0)


def test_la_deteccion_es_determinista():
    """Dos ejecuciones sobre la misma entrada dan exactamente el mismo resultado."""
    mediciones = serie(0, 30, node_id=28100) + serie(30, 60, node_id=28200)

    assert detectar_handovers(mediciones) == detectar_handovers(mediciones)
