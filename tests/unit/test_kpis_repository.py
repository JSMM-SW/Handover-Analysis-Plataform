"""
Pruebas del repositorio real de KPIs (`KpisRepository`) contra SQLite en
memoria -- a diferencia de `test_kpis_services.py` (que usa un repositorio
falso), aquí se verifica el SQL real que arma `obtener_secuencia_completa`,
en particular su ORDER BY (agrupación por sesión y desempate por
report_index, ver Paso 2 del plan de refactor de KPIs, oct 2026).

Usa el mismo patrón de `test_rsrp_source.py` para registrar en SQLite una
función `timezone(zona, timestamp)` equivalente a la de PostgreSQL, que
`KpisRepository._en_hora_local()` necesita y SQLite no trae integrada.
"""

from datetime import date, datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.modules.kpis.repository import KpisRepository
from app.shared.db.models import HandoverRecord


def _timezone_sqlite(zona: str, valor: str) -> str:
    """Emula `timezone(zona, timestamp)` de PostgreSQL para SQLite (mismo
    helper que en test_rsrp_source.py)."""
    instante = datetime.fromisoformat(valor)
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=ZoneInfo("UTC"))
    return instante.astimezone(ZoneInfo(zona)).isoformat(sep=" ")


def _crear_motor_sqlite():
    """Motor SQLite en memoria con la función `timezone` registrada."""
    engine = create_engine('sqlite://')

    @event.listens_for(engine, "connect")
    def _registrar_timezone(conexion_dbapi, _registro):
        conexion_dbapi.create_function("timezone", 2, _timezone_sqlite)

    return engine


def test_secuencia_desempata_mismo_timestamp_por_report_index():
    """Dos mediciones con el mismo timestamp_medicion se devuelven en el
    orden de su report_index, no en el orden en que se insertaron."""
    engine = _crear_motor_sqlite()
    HandoverRecord.__table__.create(engine)
    ejecucion = uuid4()
    instante = datetime(2026, 5, 5, 13, 0, 0, tzinfo=timezone.utc)  # 08:00 local

    with Session(engine) as session:
        session.add(HandoverRecord(
            execution_id=ejecucion, timestamp_medicion=instante, cell_id=20, tecnologia=1,
            rssi=-80, rsrp=-90, report_index=2, archivo_origen='Session.csv', origen_formato='csv',
        ))
        session.add(HandoverRecord(
            execution_id=ejecucion, timestamp_medicion=instante, cell_id=10, tecnologia=1,
            rssi=-80, rsrp=-90, report_index=1, archivo_origen='Session.csv', origen_formato='csv',
        ))
        session.commit()

        secuencia = KpisRepository(session).obtener_secuencia_completa(date(2026, 5, 5), date(2026, 5, 5))

        assert [registro[0] for registro in secuencia] == [10, 20]  # report_index 1 antes que 2
    engine.dispose()


def test_secuencia_agrupa_por_sesion_antes_que_por_tiempo():
    """Dos sesiones con mediciones intercaladas en el tiempo salen
    agrupadas por sesión en el resultado (no mezcladas por timestamp) --
    es lo que le permite a services.py detectar handovers por sesión sin
    reordenar nada."""
    engine = _crear_motor_sqlite()
    HandoverRecord.__table__.create(engine)
    sesion_a, sesion_b = uuid4(), uuid4()
    base = datetime(2026, 5, 5, 13, 0, 0, tzinfo=timezone.utc)  # 08:00 local

    with Session(engine) as session:
        # Sesión B se registra primero en la BD pero ocurre intercalada en el tiempo.
        session.add(HandoverRecord(
            execution_id=sesion_b, timestamp_medicion=base, cell_id=50, tecnologia=1,
            rssi=-80, rsrp=-90, report_index=1, archivo_origen='Session.csv', origen_formato='csv',
        ))
        session.add(HandoverRecord(
            execution_id=sesion_a, timestamp_medicion=base, cell_id=10, tecnologia=1,
            rssi=-80, rsrp=-90, report_index=1, archivo_origen='Session.csv', origen_formato='csv',
        ))
        session.commit()

        secuencia = KpisRepository(session).obtener_secuencia_completa(date(2026, 5, 5), date(2026, 5, 5))

        # Agrupadas por sesión (execution_id), no por orden de inserción ni timestamp puro.
        execution_ids = [registro[6] for registro in secuencia]
        assert execution_ids == sorted(execution_ids, key=str)
    engine.dispose()
