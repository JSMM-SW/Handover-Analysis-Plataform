"""
Pruebas de integración de la consulta de mediciones contra el esquema real de Supabase (BLQ-21).

Comprueban que el SQL que construye el repositorio es válido para PostgreSQL tanto con el esquema
que hoy tiene `handover_record` como con el esquema antiguo de `develop`. Se omiten si no hay
conexión a la base de datos.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.modules.visualizacion_temporal.repository import (
    VisualizacionTemporalRepository,
    construir_sql_mediciones,
    invalidar_cache_esquema,
)
from tests.unit.test_vt_esquema_etl import ESQUEMA_POBRE


@pytest.fixture(scope="module")
def db():
    from app.shared.db.database import SessionLocal

    try:
        sesion = SessionLocal()
        columnas = {
            c
            for (c,) in sesion.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'handover_record'"
                )
            )
        }
    except Exception as exc:  # noqa: BLE001 - sin BD la suite debe seguir corriendo
        pytest.skip(f"Sin conexión a la base de datos: {exc}")

    if not columnas:
        pytest.skip("handover_record no existe en esta base de datos")

    sesion.info["columnas_etl"] = columnas
    yield sesion
    sesion.close()


def _ejecutar(db, sql):
    return db.execute(text(f"SELECT * FROM (\n{sql}\n) AS m LIMIT 5")).mappings().all()


def test_la_consulta_con_el_esquema_actual_es_valida(db):
    columnas = db.info["columnas_etl"]
    filas = _ejecutar(db, construir_sql_mediciones(columnas, {"execution_id", "sesion_label"}))

    assert filas is not None


def test_la_consulta_con_el_esquema_antiguo_sigue_siendo_valida(db):
    """Simula el esquema de develop usando solo el subconjunto de columnas que ya existía."""
    columnas = ESQUEMA_POBRE & db.info["columnas_etl"]
    filas = _ejecutar(db, construir_sql_mediciones(columnas))

    assert filas is not None


def test_el_repositorio_lista_sesiones_reales_con_nombre_legible(db):
    invalidar_cache_esquema()
    sesiones = VisualizacionTemporalRepository(db).listar_sesiones()

    if not sesiones:
        pytest.skip("No hay sesiones del ETL cargadas")

    assert all(s["sesion_nombre"] for s in sesiones)
    assert all(s["n_celdas"] > 0 for s in sesiones)


def test_la_tabla_de_eventos_se_lee_sin_vistas(db):
    """BLQ-23: la tabla de eventos no depende de `v_vt_evento_detalle` ni de ninguna vista."""
    sesiones = VisualizacionTemporalRepository(db).listar_sesiones()
    if not sesiones:
        pytest.skip("No hay sesiones del ETL cargadas")

    filtros = SimpleNamespace(sesion_ids=[str(sesiones[0]["sesion_id"])])
    total, filas = VisualizacionTemporalRepository(db).listar_handovers(filtros, page_size=5)

    assert total >= len(filas)
