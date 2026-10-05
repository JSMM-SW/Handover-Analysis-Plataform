"""
Pruebas de la capa de servicios del Módulo 2 (Fase 2, tarea 2.5).

Usan un **repositorio falso en memoria**: los servicios no deben saber nada de SQLAlchemy ni de
la base de datos, así que probarlos no requiere conexión (y de hecho no la hay, BLQ-05).
"""

import pytest

from app.modules.visualizacion_temporal.exceptions import (
    SesionNoEncontrada,
    SesionSinMediciones,
)
from app.modules.visualizacion_temporal.schemas import ParametrosDeteccion
from app.modules.visualizacion_temporal.services import ejecutar_deteccion
from tests.fixtures.dataset_sintetico import (
    SESION_ID,
    SESION_NOMBRE,
    TOTAL_HANDOVERS_ESPERADOS,
)
from tests.unit.test_detector_verdad_referencia import _a_mediciones


class RepositorioFalso:
    """Repositorio en memoria con la misma interfaz que el real."""

    def __init__(self, mediciones=None, cobertura=None):
        self._mediciones = mediciones if mediciones is not None else []
        self._cobertura = cobertura or []
        self.eventos_guardados = []
        self.borrados = 0
        self.parametros_recibidos = None

    def existe_sesion(self, sesion_id):
        return any(m.sesion_id == sesion_id for m in self._mediciones)

    def obtener_mediciones(self, sesion_id, desde=None, hasta=None):
        return [m for m in self._mediciones if m.sesion_id == sesion_id]

    def obtener_cobertura_parametros(self, sesion_id):
        return self._cobertura

    def borrar_handovers_de_sesion(self, sesion_id):
        self.borrados += 1
        anteriores = len(self.eventos_guardados)
        self.eventos_guardados = []
        return anteriores

    def guardar_handovers(self, eventos, parametros_deteccion):
        self.eventos_guardados = list(eventos)
        self.parametros_recibidos = parametros_deteccion
        return len(eventos)


@pytest.fixture
def repositorio():
    return RepositorioFalso(mediciones=_a_mediciones())


# ------------------------------------------------------------------------------------------------
# Camino feliz
# ------------------------------------------------------------------------------------------------


def test_la_deteccion_devuelve_el_total_de_handovers(repositorio):
    """CA3 de HU-C2-001."""
    resumen = ejecutar_deteccion(SESION_ID, ParametrosDeteccion(), repositorio)

    assert resumen.total_handovers == TOTAL_HANDOVERS_ESPERADOS
    assert resumen.sesion_id == SESION_ID
    assert resumen.sesion_nombre == SESION_NOMBRE


def test_la_deteccion_persiste_los_eventos(repositorio):
    ejecutar_deteccion(SESION_ID, ParametrosDeteccion(), repositorio)

    assert len(repositorio.eventos_guardados) == TOTAL_HANDOVERS_ESPERADOS


def test_el_resumen_desglosa_por_tipo_y_por_tecnologia(repositorio):
    resumen = ejecutar_deteccion(SESION_ID, ParametrosDeteccion(), repositorio)

    assert sum(resumen.por_tipo.values()) == TOTAL_HANDOVERS_ESPERADOS
    assert resumen.por_tipo["inter_rat"] == 2
    assert resumen.por_tecnologia["LTE->WCDMA"] == 1
    assert resumen.por_tecnologia["WCDMA->LTE"] == 1


def test_el_resumen_cuenta_ping_pong_y_confianza_baja(repositorio):
    resumen = ejecutar_deteccion(SESION_ID, ParametrosDeteccion(), repositorio)

    assert resumen.total_ping_pong == 1
    assert resumen.total_confianza_baja == 1


def test_el_resumen_incluye_radiobases_y_ventana_temporal(repositorio):
    resumen = ejecutar_deteccion(SESION_ID, ParametrosDeteccion(), repositorio)

    assert resumen.radiobases_involucradas == 8
    assert resumen.ventana_inicio is not None
    assert resumen.ventana_fin > resumen.ventana_inicio


def test_el_resumen_registra_los_parametros_usados(repositorio):
    parametros = ParametrosDeteccion(muestras_confirmacion=3, max_gap_s=45)

    resumen = ejecutar_deteccion(SESION_ID, parametros, repositorio)

    assert resumen.parametros_usados.muestras_confirmacion == 3
    assert repositorio.parametros_recibidos["muestras_confirmacion"] == 3
    assert repositorio.parametros_recibidos["max_gap_s"] == 45


# ------------------------------------------------------------------------------------------------
# Cobertura de parámetros RF — decisión D-5
# ------------------------------------------------------------------------------------------------


def test_la_cobertura_incluye_siempre_los_cinco_parametros(repositorio):
    resumen = ejecutar_deteccion(SESION_ID, ParametrosDeteccion(), repositorio)

    parametros = [c.parametro for c in resumen.cobertura_parametros]
    assert parametros == ["rsrp_dbm", "rsrq_db", "rssnr_db", "rscp_dbm", "rssi_dbm"]


def test_un_parametro_sin_ninguna_medida_se_marca_como_no_disponible(repositorio):
    """Es lo que permite a la interfaz decir 'sin datos válidos' en lugar de no mostrar nada."""
    resumen = ejecutar_deteccion(SESION_ID, ParametrosDeteccion(), repositorio)
    por_nombre = {c.parametro: c for c in resumen.cobertura_parametros}

    # El dataset sintético no tiene RSSI de GSM en ninguna medición.
    assert por_nombre["rssi_dbm"].disponible is False
    assert por_nombre["rssi_dbm"].n_validos == 0

    # RSRP sí, en casi todas.
    assert por_nombre["rsrp_dbm"].disponible is True
    assert por_nombre["rsrp_dbm"].pct_validos > 50


def test_la_cobertura_de_sinr_es_parcial_en_el_dataset_sintetico(repositorio):
    resumen = ejecutar_deteccion(SESION_ID, ParametrosDeteccion(), repositorio)
    sinr = next(c for c in resumen.cobertura_parametros if c.parametro == "rssnr_db")

    assert sinr.disponible is True
    assert 0 < sinr.n_validos < sinr.n_mediciones
    assert sinr.etiqueta == "RSSNR (dB)"


def test_la_cobertura_de_la_vista_tiene_prioridad_sobre_el_calculo_local():
    """Las cifras de la vista cubren toda la sesión, no solo las mediciones leídas."""
    repositorio = RepositorioFalso(
        mediciones=_a_mediciones(),
        cobertura=[{"parametro": "rssnr_db", "n_validos": 0, "n_mediciones": 86398, "pct_validos": 0.0}],
    )

    resumen = ejecutar_deteccion(SESION_ID, ParametrosDeteccion(), repositorio)
    sinr = next(c for c in resumen.cobertura_parametros if c.parametro == "rssnr_db")

    assert sinr.n_mediciones == 86398
    assert sinr.n_validos == 0
    assert sinr.disponible is False


# ------------------------------------------------------------------------------------------------
# Idempotencia
# ------------------------------------------------------------------------------------------------


def test_recalcular_borra_los_eventos_previos(repositorio):
    ejecutar_deteccion(SESION_ID, ParametrosDeteccion(recalcular=True), repositorio)
    ejecutar_deteccion(SESION_ID, ParametrosDeteccion(recalcular=True), repositorio)

    assert repositorio.borrados == 2
    assert len(repositorio.eventos_guardados) == TOTAL_HANDOVERS_ESPERADOS


def test_sin_recalcular_no_se_borra_nada(repositorio):
    ejecutar_deteccion(SESION_ID, ParametrosDeteccion(recalcular=False), repositorio)

    assert repositorio.borrados == 0


def test_dos_ejecuciones_seguidas_dan_el_mismo_resumen(repositorio):
    primera = ejecutar_deteccion(SESION_ID, ParametrosDeteccion(), repositorio)
    segunda = ejecutar_deteccion(SESION_ID, ParametrosDeteccion(), repositorio)

    assert primera.total_handovers == segunda.total_handovers
    assert primera.por_tipo == segunda.por_tipo


# ------------------------------------------------------------------------------------------------
# Errores de dominio — no HTTPException (eso es cosa del router)
# ------------------------------------------------------------------------------------------------


def test_sesion_inexistente_lanza_error_de_dominio(repositorio):
    with pytest.raises(SesionNoEncontrada) as excinfo:
        ejecutar_deteccion("no-existe", ParametrosDeteccion(), repositorio)

    assert excinfo.value.sesion_id == "no-existe"


def test_sesion_sin_mediciones_lanza_error_de_dominio():
    class RepositorioVacio(RepositorioFalso):
        def existe_sesion(self, sesion_id):
            return True

    with pytest.raises(SesionSinMediciones):
        ejecutar_deteccion(SESION_ID, ParametrosDeteccion(), RepositorioVacio())


def test_sesion_con_mediciones_sin_identidad_lanza_error_de_dominio():
    """Mediciones sin `cid`: la sesión existe pero no sirve para el análisis temporal."""
    from dataclasses import replace

    sin_identidad = [replace(m, cid=None) for m in _a_mediciones()]

    with pytest.raises(SesionSinMediciones):
        ejecutar_deteccion(SESION_ID, ParametrosDeteccion(), RepositorioFalso(sin_identidad))


def _modulos_importados(modulo) -> set[str]:
    """Nombres de los módulos que importa un archivo, leídos de su AST.

    Se analiza el árbol sintáctico y no el texto: buscar la cadena "fastapi" en el código daría
    falsos positivos por los comentarios, que precisamente explican por qué no se importa.
    """
    import ast
    import inspect

    arbol = ast.parse(inspect.getsource(modulo))
    importados: set[str] = set()

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            importados.add(nodo.module)

    return importados


def test_los_servicios_no_dependen_de_fastapi_ni_de_sqlalchemy():
    """La capa 3 no conoce el transporte ni el motor de base de datos (docs/02)."""
    from app.modules.visualizacion_temporal import services

    importados = _modulos_importados(services)

    assert not any(m.startswith("fastapi") for m in importados)
    assert not any(m.startswith("sqlalchemy") for m in importados)


def test_el_detector_no_importa_nada_del_proyecto():
    """El detector debe ser puro para poder defenderlo como algoritmo (docs/02)."""
    from app.modules.visualizacion_temporal import detector

    importados = _modulos_importados(detector)

    assert not any(m.startswith("app") for m in importados), (
        f"El detector debe ser puro; importa {importados}"
    )
    assert not any(m.startswith(("fastapi", "sqlalchemy")) for m in importados)


def test_el_repositorio_es_la_unica_capa_con_sql():
    """Regla 2 de CLAUDE.md: solo el repositorio toca la base de datos."""
    from app.modules.visualizacion_temporal import repository, schemas

    assert any(m.startswith("sqlalchemy") for m in _modulos_importados(repository))
    assert not any(m.startswith("sqlalchemy") for m in _modulos_importados(schemas))


def test_solo_el_repositorio_conoce_las_tablas_del_modulo_1():
    """Aislamiento por contrato (regla 2): el esquema del ETL solo se nombra en repository.py."""
    import inspect

    from app.modules.visualizacion_temporal import (
        detector,
        exceptions,
        lttb,
        repository,
        router,
        schemas,
        services,
    )

    for modulo in (detector, exceptions, lttb, router, schemas, services):
        codigo = inspect.getsource(modulo)
        for tabla_ajena in ("handover_record", "etl_execution"):
            assert tabla_ajena not in codigo, (
                f"{modulo.__name__} no debe nombrar la tabla {tabla_ajena} del Módulo 1"
            )

    assert repository.TABLA_MEDICIONES_ETL == "handover_record"


def test_el_repositorio_solo_escribe_en_eventos_handover():
    """Las tablas del Módulo 1 se leen y nunca se modifican."""
    import inspect
    import re

    from app.modules.visualizacion_temporal import repository

    codigo = inspect.getsource(repository)
    escrituras = re.findall(
        r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE|ALTER\s+TABLE|DROP\s+\w+)\s+(\w+)",
        codigo,
        flags=re.IGNORECASE,
    )

    assert escrituras, "No se encontró ninguna escritura; el patrón de la prueba quedó obsoleto"
    assert set(escrituras) == {"eventos_handover"}

    # Ni rastro de la vista antigua: ya no hay que reejecutar SQL al cambiar el ETL (BLQ-21).
    assert "v_vt_medicion" not in codigo
