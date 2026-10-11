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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.modules.kpis.repository import KpisRepository
from app.shared.db.models import EtlExecution, HandoverRecord


@compiles(JSONB, "sqlite")
def _jsonb_como_json_en_sqlite(_tipo, _compilador, **_kw):
    """`EtlExecution.warnings`/`.errors` son JSONB (tipo de PostgreSQL);
    SQLite no lo sabe compilar al crear la tabla, así que se traduce a
    JSON (SQLite lo trata como TEXT) solo para este motor de pruebas."""
    return "JSON"




def _timezone_sqlite(zona: str, valor: str | None) -> str | None:
    """Emula `timezone(zona, timestamp)` de PostgreSQL para SQLite (mismo
    helper que en test_rsrp_source.py). `valor` puede ser None cuando viene
    de un LEFT OUTER JOIN sin coincidencias (ej. una sesión sin mediciones
    en handover_record) -- igual que en Postgres, timezone(zona, NULL)
    debe devolver NULL, no lanzar una excepción."""
    if valor is None:
        return None
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


def test_listar_sesiones_incluye_primera_y_ultima_medicion():
    """Una sesión con varias mediciones devuelve la primera y la última
    (hora local, no UTC); una sesión sin ninguna medición en
    handover_record devuelve None/None (outerjoin, no inner join)."""
    engine = _crear_motor_sqlite()
    EtlExecution.__table__.create(engine)
    HandoverRecord.__table__.create(engine)
    con_datos = uuid4()
    sin_datos = uuid4()

    with Session(engine) as session:
        session.add(EtlExecution(
            execution_id=con_datos, sesion_label=1, filename='ConDatos.csv',
            status='completed', records_valid=3,
        ))
        session.add(EtlExecution(
            execution_id=sin_datos, sesion_label=2, filename='SinDatos.csv',
            status='completed', records_valid=0,
        ))
        session.add(HandoverRecord(
            execution_id=con_datos, timestamp_medicion=datetime(2026, 5, 5, 13, 0, 0, tzinfo=timezone.utc),
            cell_id=1, tecnologia=1, rssi=-80, rsrp=-90,
            archivo_origen='ConDatos.csv', origen_formato='csv',
        ))
        session.add(HandoverRecord(
            execution_id=con_datos, timestamp_medicion=datetime(2026, 5, 5, 20, 0, 0, tzinfo=timezone.utc),
            cell_id=2, tecnologia=1, rssi=-80, rsrp=-90,
            archivo_origen='ConDatos.csv', origen_formato='csv',
        ))
        session.commit()

        filas = KpisRepository(session).listar_sesiones()

        por_sesion = {ejecucion.sesion_label: (primera, ultima) for ejecucion, primera, ultima in filas}

        # 13:00 y 20:00 UTC -> 08:00 y 15:00 hora local de Ecuador (UTC-5).
        primera_con_datos, ultima_con_datos = por_sesion[1]
        assert str(primera_con_datos).startswith("2026-05-05 08:00")
        assert str(ultima_con_datos).startswith("2026-05-05 15:00")
        assert por_sesion[2] == (None, None)
    engine.dispose()
