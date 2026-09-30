"""
Pruebas del dataset sintético de referencia del Módulo 2 (Fase 1).

Estas pruebas no validan el detector —todavía no existe—, sino la **verdad de
referencia** contra la que se validará en la Fase 2. Si el fixture dejara de
cumplir lo que declara, las pruebas del detector estarían midiendo contra una
regla equivocada sin que nadie se enterase.
"""

import pathlib

import pytest

from tests.fixtures.dataset_sintetico import (
    CELDAS_DISTINTAS_ESPERADAS,
    EVENTOS_ESPERADOS,
    HUECO_FIN_S,
    HUECO_INICIO_S,
    SESION_ID,
    SESION_NOMBRE,
    TOTAL_HANDOVERS_ESPERADOS,
    TOTAL_MEDICIONES_ESPERADAS,
    celda_por_etiqueta,
    generar_mediciones,
    generar_sql,
    verificar_coherencia,
)

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SQL_DATOS_PRUEBA = RAIZ / "docs" / "sql" / "03_datos_prueba.sql"


def test_el_dataset_cumple_lo_que_declara():
    """Comprobación integral: tramos, huecos, orden y eventos declarados."""
    verificar_coherencia()


def test_numero_de_mediciones_y_celdas():
    mediciones = generar_mediciones()
    assert len(mediciones) == TOTAL_MEDICIONES_ESPERADAS
    assert len({m["celda_clave"] for m in mediciones}) == CELDAS_DISTINTAS_ESPERADAS


def test_todas_las_mediciones_pertenecen_a_la_sesion():
    mediciones = generar_mediciones()
    assert {m["sesion_id"] for m in mediciones} == {SESION_ID}
    assert {m["sesion_nombre"] for m in mediciones} == {SESION_NOMBRE}


def test_hay_ocho_handovers_declarados():
    assert TOTAL_HANDOVERS_ESPERADOS == 8
    assert len(EVENTOS_ESPERADOS) == 8


def test_la_verdad_de_referencia_cubre_todos_los_casos_del_plan():
    """La Fase 1 exige que el dataset contenga ciertos casos a propósito."""
    tipos = [e.tipo_evento for e in EVENTOS_ESPERADOS]

    assert tipos.count("intra_frecuencia") >= 1
    assert tipos.count("inter_frecuencia") >= 1
    assert tipos.count("inter_rat") >= 1, "Falta el handover inter-RAT"
    assert any(e.ping_pong for e in EVENTOS_ESPERADOS), "Falta la secuencia ping-pong"
    assert any(e.confianza == "baja" for e in EVENTOS_ESPERADOS), (
        "Falta el caso de identidad incompleta (confianza baja)"
    )


def test_el_ping_pong_vuelve_a_la_celda_de_origen_anterior():
    """A -> B -> A: el destino del evento ping-pong es el origen del anterior."""
    indice = next(i for i, e in enumerate(EVENTOS_ESPERADOS) if e.ping_pong)
    assert indice > 0, "El ping-pong no puede ser el primer evento"

    anterior, actual = EVENTOS_ESPERADOS[indice - 1], EVENTOS_ESPERADOS[indice]
    assert actual.destino == anterior.origen
    assert actual.segundo - anterior.segundo <= 10


def test_el_hueco_temporal_no_cambia_de_celda():
    """Un salto de captura no debe poder confundirse con un handover."""
    mediciones = {m["segundo_relativo"]: m for m in generar_mediciones()}

    assert HUECO_FIN_S - HUECO_INICIO_S == 30
    antes, despues = mediciones[HUECO_INICIO_S - 1], mediciones[HUECO_FIN_S]
    assert antes["celda_clave"] == despues["celda_clave"]

    # Y ningún evento declarado cae dentro del hueco.
    assert not any(HUECO_INICIO_S <= e.segundo < HUECO_FIN_S for e in EVENTOS_ESPERADOS)


def test_identidad_de_celda_en_lte_usa_el_eci():
    """En LTE la clave es node_id*256+cid, no el cid suelto (docs/06 §3.1)."""
    celda = celda_por_etiqueta("A")
    assert celda.tech == "LTE"
    assert celda.clave == f"LTE:{celda.node_id * 256 + celda.cid}"


def test_identidad_de_celda_sin_node_id_degrada_la_confianza():
    """Sin `node_id` no se puede calcular el ECI: se cae a (tech, lac_tac, cid)."""
    celda = celda_por_etiqueta("N")
    assert celda.node_id is None
    assert celda.confianza == "baja"

    # Forma de reserva, de tres partes — no la forma ECI, de dos.
    assert celda.clave == f"LTE:{celda.lac_tac}:{celda.cid}"
    assert celda.clave.count(":") == 2


def test_identidad_de_celda_en_wcdma_no_usa_eci():
    celda = celda_por_etiqueta("W")
    assert celda.tech == "WCDMA"
    assert celda.clave == f"WCDMA:{celda.lac_tac}:{celda.cid}"


@pytest.mark.parametrize("parametro", ["rsrp_dbm", "rsrq_db", "rssnr_db"])
def test_los_parametros_rf_ausentes_son_none_nunca_cero(parametro):
    """`None` -> NULL en SQL. Un 0 sería indistinguible de una medida real."""
    valores = [m[parametro] for m in generar_mediciones()]
    assert any(v is None for v in valores), f"{parametro} nunca falta: caso sin datos no cubierto"
    assert all(v is None or isinstance(v, int) for v in valores)


def test_rssnr_esta_parcialmente_disponible():
    """El dataset ejercita a la vez la ruta 'con SINR' y la ruta 'sin SINR'."""
    valores = [m["rssnr_db"] for m in generar_mediciones()]
    con_dato = sum(1 for v in valores if v is not None)

    assert con_dato > 0, "Falta el tramo con medida de SINR"
    assert con_dato < len(valores), "Falta el tramo sin medida de SINR"


def test_la_degradacion_de_señal_precede_a_cada_handover():
    """Antes de cada HO la señal de la celda origen debe haber empeorado."""
    mediciones = {m["segundo_relativo"]: m for m in generar_mediciones()}

    for evento in EVENTOS_ESPERADOS:
        origen = celda_por_etiqueta(evento.origen)
        if origen.rsrp_base is None:
            continue  # la celda WCDMA no reporta RSRP

        entrada = next(
            s for s in sorted(mediciones) if mediciones[s]["celda_clave"] == origen.clave
        )
        rsrp_al_entrar = mediciones[entrada]["rsrp_dbm"]
        rsrp_al_salir = mediciones[evento.segundo - 1]["rsrp_dbm"]

        assert rsrp_al_salir <= rsrp_al_entrar, (
            f"La señal de {evento.origen} no se degrada antes del HO del segundo {evento.segundo}"
        )


def test_el_sql_de_datos_de_prueba_esta_sincronizado():
    """El .sql versionado debe coincidir con lo que produce el generador.

    Si esta prueba falla, regenera el archivo:
        python -m tests.fixtures.dataset_sintetico

    `docs/sql/` no se versiona (es documentación local del autor), así que en un clon sin esa
    carpeta la prueba se omite en lugar de fallar.
    """
    if not SQL_DATOS_PRUEBA.exists():
        pytest.skip(f"{SQL_DATOS_PRUEBA} no existe en este entorno (docs/sql/ no se versiona)")
    assert SQL_DATOS_PRUEBA.read_text(encoding="utf-8") == generar_sql(), (
        "docs/sql/03_datos_prueba.sql está desactualizado respecto al generador"
    )


def test_el_sql_declara_la_verdad_de_referencia():
    """El script debe documentar cuántos HO se esperan (criterio de cierre de la Fase 1)."""
    # Validate the generated script even in clones without the author's local docs/sql/.
    sql = generar_sql()

    assert f"HANDOVERS ESPERADOS : {TOTAL_HANDOVERS_ESPERADOS}" in sql
    assert SESION_ID in sql
    assert "muestras_confirmacion" in sql
