"""
Pruebas de integración de guardar_reporte_historial/listar_historial_reportes
(HU-010, Paso 13 del plan de refactor) contra el esquema real de Supabase.

A diferencia de los demás repositorios de KPIs (solo lectura), estas pruebas
escriben en la base de datos real -- cada una borra la fila que crea al
terminar, para no dejar datos de prueba acumulándose en kpi_reporte_historial.
Se omiten si no hay conexión a la base de datos.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.kpis.repository import KpisRepository


@pytest.fixture
def db():
    from app.shared.db.database import SessionLocal

    try:
        sesion = SessionLocal()
        sesion.execute(__import__("sqlalchemy").text("SELECT 1 FROM kpi_reporte_historial LIMIT 1"))
    except Exception as exc:  # noqa: BLE001 - sin BD la suite debe seguir corriendo
        pytest.skip(f"Sin conexión a la base de datos o tabla inexistente: {exc}")

    yield sesion
    sesion.rollback()
    sesion.close()


def _datos_reporte(**overrides):
    base = dict(
        nombre_archivo="Reporte_Handovers_2026-01-01_al_2026-01-31.pdf",
        fecha_inicio="2026-01-01",
        fecha_fin="2026-01-31",
        tecnologia=[1],
        franja=[],
        sesion_label=[],
        periodicidad="diario",
        periodo_seleccionado=None,
        resultados={"total_handovers": 10, "tasa_exito": 80.0},
        parametros_calculo={
            "hueco_maximo_s": 10,
            "ping_pong_ventana_s": 60,
            "uho_rssi_min_dbm": -100,
            "uho_rsrq_min_db": -15,
        },
    )
    base.update(overrides)
    return base


def test_guardar_y_listar_reporte_historial(db):
    repositorio = KpisRepository(db)
    datos = _datos_reporte()

    guardado = repositorio.guardar_reporte_historial(**datos)
    try:
        assert guardado.id is not None
        assert guardado.fecha_generacion is not None
        assert guardado.nombre_archivo == datos["nombre_archivo"]
        assert guardado.tecnologia == datos["tecnologia"]
        assert guardado.resultados == datos["resultados"]
        assert guardado.parametros_calculo == datos["parametros_calculo"]

        historial = repositorio.listar_historial_reportes(limit=200)
        assert any(fila.id == guardado.id for fila in historial)
    finally:
        db.query(type(guardado)).filter(type(guardado).id == guardado.id).delete()
        db.commit()


def test_guardar_reporte_resuelve_sesion_label_a_execution_id(db):
    """Sin sesiones seleccionadas (lista vacía), sesion_execution_id debe
    quedar vacío también -- no se inventa nada cuando el filtro es "todas"."""
    repositorio = KpisRepository(db)
    datos = _datos_reporte(sesion_label=[])

    guardado = repositorio.guardar_reporte_historial(**datos)
    try:
        assert guardado.sesion_execution_id == []
    finally:
        db.query(type(guardado)).filter(type(guardado).id == guardado.id).delete()
        db.commit()


def test_guardar_reporte_rechaza_tecnologia_invalida(db):
    """El CHECK chk_kpi_reporte_tecnologia debe rechazar valores fuera de {1,2,3}."""
    repositorio = KpisRepository(db)
    datos = _datos_reporte(tecnologia=[99])

    with pytest.raises(IntegrityError):
        repositorio.guardar_reporte_historial(**datos)
