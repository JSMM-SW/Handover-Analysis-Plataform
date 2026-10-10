from datetime import date, datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.modules.kpis.repository import KpisRepository
from app.modules.kpis.services import calcular_metricas_globales_dia
from app.modules.visualizacion_temporal.repository import construir_sql_mediciones
from app.shared.db.models import HandoverRecord


def test_temporal_uses_strongest_as_rsrp_without_rssi_fallback():
    columns = {'id_registro', 'execution_id', 'timestamp_medicion', 'rssi', 'rsrp'}
    sql = construir_sql_mediciones(columns)
    assert 'h."rsrp"::smallint AS rsrp_dbm' in sql
    assert 'h."rssi"::smallint AS rssi_dbm' in sql
    assert 'NULL::smallint AS rscp_dbm' in sql
    sql = construir_sql_mediciones(columns - {'rsrp'})
    assert 'NULL::smallint AS rsrp_dbm' in sql


def _timezone_sqlite(zona: str, valor: str) -> str:
    """Emula la función `timezone(zona, timestamp)` de PostgreSQL para que
    los tests unitarios puedan usar SQLite en memoria en vez de una base
    real. `KpisRepository._en_hora_local()` usa `func.timezone(...)` (ver
    repository.py) -- es válido en Postgres pero SQLite no la trae
    integrada, así que hay que registrársela a mano sobre la conexión de
    prueba.

    SQLAlchemy guarda los timestamptz como texto ISO 8601 en SQLite; se
    interpretan como UTC (igual que timestamptz en Postgres, que siempre
    almacena en UTC) y se convierten a la zona pedida.
    """
    instante = datetime.fromisoformat(valor)
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=ZoneInfo("UTC"))
    return instante.astimezone(ZoneInfo(zona)).isoformat(sep=" ")


def _crear_motor_sqlite():
    """Motor SQLite en memoria con la función `timezone` registrada, listo
    para usarse con `KpisRepository` sin tocar Supabase."""
    engine = create_engine('sqlite://')

    @event.listens_for(engine, "connect")
    def _registrar_timezone(conexion_dbapi, _registro):
        conexion_dbapi.create_function("timezone", 2, _timezone_sqlite)

    return engine


@pytest.mark.parametrize('signals, average, critical, risk', [
    ([-120, -80, None], -100, 1, 50),
    ([None], None, None, None),
    ([], None, None, None),
])
def test_daily_rsrp_uses_strongest_and_excludes_missing_values(signals, average, critical, risk):
    engine = _crear_motor_sqlite()
    HandoverRecord.__table__.create(engine)
    with Session(engine) as session:
        for signal in signals:
            session.add(HandoverRecord(
                execution_id=uuid4(), timestamp_medicion=datetime(2026, 9, 23, tzinfo=timezone.utc),
                cell_id=1, tecnologia=1, rssi=-50, rsrp=signal,
                archivo_origen='Session.csv', origen_formato='csv',
            ))
        session.commit()
        result = calcular_metricas_globales_dia(date(2026, 9, 23), KpisRepository(session))
        assert result.total_mediciones == len(signals)
        assert result.promedio_rsrp == average
        assert result.eventos_criticos == critical
        assert result.tasa_riesgo == risk
    engine.dispose()
