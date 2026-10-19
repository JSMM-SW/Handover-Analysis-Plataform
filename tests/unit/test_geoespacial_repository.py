"""Exercise the session summary query without connecting to the shared database."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import UUID
import pytest

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.visualizacion_geoespacial.repository import GeoespacialRepository, RECORD_COLUMNS, as_temporal_measurement
from app.shared.db.models import HandoverRecord


def raw_record(index, session_id=UUID(int=1), **changes):
    values = dict.fromkeys(RECORD_COLUMNS)
    values.update(id_registro=UUID(int=index + 1), execution_id=session_id,
                  timestamp_medicion=datetime(2026, 5, 5) + timedelta(seconds=index),
                  cell_id=10 if index < 2 else 20, tecnologia=1, node_id=100,
                  report_index=index, hoja_origen=None, latitud=-0.2, longitud=-78.5)
    values.update(changes)
    return values


def result(rows):
    return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))


def test_filter_changes_and_different_requests_reuse_versioned_session(monkeypatch):
    from app.modules.visualizacion_geoespacial.analysis_cache import AnalysisCache
    cache = AnalysisCache(ttl=120, prepare=lambda data: None,
                          cost=lambda data: len(data[0]) + len(data[1]), snapshot=lambda data: data)
    monkeypatch.setattr('app.modules.visualizacion_geoespacial.repository.session_cache', cache)
    bind = type('TestBind', (), {'dialect': SimpleNamespace(name='sqlite')})()
    calls = []
    version = [4, datetime(2026, 5, 5)]
    session_id = UUID(int=100)

    def execute(query):
        if query.column_descriptions[0]['name'] == 'execution_id':
            return result([dict(execution_id=session_id, records_valid=version[0], processing_date=version[1])])
        calls.append(query)
        return result([raw_record(i, session_id) for i in range(4)])

    def request(start=None):
        repository = GeoespacialRepository(SimpleNamespace(
            execute=execute, rollback=lambda: None, get_bind=lambda: bind))
        repository.execution(session_id)
        rows = repository.measurements([session_id], None, desde=start)
        return rows, repository.handovers([session_id])

    first_rows, first_events = request()
    filtered_rows, filtered_events = request(datetime(2026, 5, 5, 0, 1, 2))
    assert len(first_rows) == 4 and len(filtered_rows) == 2
    assert first_events == filtered_events and len(first_events) == 1
    assert len(calls) == 1
    assert not hasattr(first_rows[0], '__dict__')
    version[1] += timedelta(seconds=1)
    request()
    assert len(calls) == 2


def test_postgres_cursor_reads_all_batches_with_one_query_and_releases_connection():
    queries, closed, rollbacks = [], [], []
    batches = [[raw_record(i) for i in range(3)], [raw_record(3)]]
    def execute(query):
        queries.append(query)
        assert query.get_execution_options()['yield_per'] == 5000
        return SimpleNamespace(mappings=lambda: SimpleNamespace(partitions=lambda size: iter(batches)),
                               close=lambda: closed.append(True))
    db = SimpleNamespace(execute=execute, rollback=lambda: rollbacks.append(True),
                         get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name='postgresql')))
    rows = GeoespacialRepository(db).measurements([UUID(int=1)], None)
    assert len(rows) == 4
    assert len(queries) == len(closed) == len(rollbacks) == 1


def test_interrupted_cursor_restarts_without_duplicate_or_partial_rows():
    queries, closed, rollbacks = [], [], []
    def partitions(size):
        yield [raw_record(0)]
        if len(queries) == 1:
            raise OperationalError('read', {}, Exception('disconnect'), connection_invalidated=True)
        yield [raw_record(1)]
    def execute(query):
        queries.append(query)
        return SimpleNamespace(mappings=lambda: SimpleNamespace(partitions=partitions),
                               close=lambda: closed.append(True))
    db = SimpleNamespace(execute=execute, rollback=lambda: rollbacks.append(True))
    rows = GeoespacialRepository(db)._stream_records(UUID(int=1))
    assert [row.id_registro for row in rows] == [UUID(int=1), UUID(int=2)]
    assert len(queries) == len(closed) == len(rollbacks) == 2


def test_measurement_query_has_no_analysis_row_limit(monkeypatch):
    monkeypatch.setattr('app.modules.visualizacion_geoespacial.repository.READ_BATCH_SIZE', 10000)
    queries = []
    def execute(query):
        start = len(queries) * 10000
        queries.append(query)
        return result([raw_record(i) for i in range(start, min(start + 10000, 60001))])
    rows = GeoespacialRepository(SimpleNamespace(execute=execute, rollback=lambda: None)).measurements([UUID(int=1)], None)
    assert len(rows) == 60001
    assert len(queries) == 7
    assert len({row.id_registro for row in rows}) == 60001


def test_availability_merges_adjacent_minutes_but_preserves_gaps_and_days():
    rows = [{'minuto': datetime(2026, 5, 5, 8, 0), 'n_mediciones': 2},
            {'minuto': datetime(2026, 5, 5, 8, 1), 'n_mediciones': 3},
            {'minuto': datetime(2026, 5, 5, 10, 0), 'n_mediciones': 1},
            {'minuto': datetime(2026, 5, 6, 11, 0), 'n_mediciones': 4}]
    db = SimpleNamespace(execute=lambda query: result(rows), rollback=lambda: None)
    assert GeoespacialRepository(db).available_days([UUID(int=1)]) == [
        {'fecha': '2026-05-05', 'n_mediciones': 6, 'franjas': [
            {'inicio': '08:00', 'fin': '08:01'}, {'inicio': '10:00', 'fin': '10:00'}]},
        {'fecha': '2026-05-06', 'n_mediciones': 4, 'franjas': [{'inicio': '11:00', 'fin': '11:00'}]},
    ]


def test_handovers_reuse_rows_from_complete_independent_sessions(monkeypatch):
    calls = []
    sessions = [UUID(int=100), UUID(int=200)]
    repository = GeoespacialRepository(None)
    def read(query):
        session_id = sessions[len(calls)]
        calls.append(query)
        return [raw_record(i, session_id) for i in range(4)]
    monkeypatch.setattr(repository, '_read', read)
    # Map interval selects only the destination, but detection sees all rows.
    rows = repository.measurements(sessions, None, desde=datetime(2026, 5, 5, 0, 1, 2))
    assert len(rows) == 4
    events = repository.handovers(sessions)
    assert len(calls) == 2
    assert len(events) == 2
    assert {event.sesion_id for event in events} == {str(session) for session in sessions}


def test_temporal_adapter_preserves_raw_identity_and_original_signals():
    row = SimpleNamespace(**raw_record(0, cid=42, lac_tac_raw=7, tac=8, tech='WCDMA',
                                       rssi=-75, rsrp=-95, rsrq=-12, rssnr=10))
    measurement = as_temporal_measurement(row)
    assert (measurement.cid, measurement.lac_tac, measurement.tech) == (42, 7, 'WCDMA')
    assert (measurement.rssi_dbm, measurement.rsrp_dbm, measurement.rsrq_db, measurement.rssnr_db) == (-75, -95, -12, 10)


@pytest.mark.parametrize('stream', [False, True])
def test_keyset_batches_preserve_same_time_and_null_report_indices(monkeypatch, stream):
    monkeypatch.setattr('app.modules.visualizacion_geoespacial.repository.READ_BATCH_SIZE', 2)
    engine = create_engine('sqlite://')
    HandoverRecord.__table__.create(engine)
    session_id = UUID('aaaaaaaa-0000-0000-0000-000000000001')
    rows = [raw_record(i, session_id, id_registro=UUID(f'bbbbbbbb-0000-0000-0000-{i + 1:012x}'),
                       report_index=index, timestamp_medicion=datetime(2026, 5, 5))
            | {'archivo_origen': 'session.csv', 'origen_formato': 'csv'}
            for i, index in enumerate([None, 1, None, 0, 2])]
    with engine.begin() as connection:
        connection.execute(HandoverRecord.__table__.insert(), rows)
    with Session(engine) as session:
        repository = GeoespacialRepository(session)
        loaded = repository._stream_records(session_id) if stream else repository.measurements([session_id], None)
    assert [row.id_registro for row in loaded] == [rows[i - 1]['id_registro'] for i in [4, 2, 5, 1, 3]]
    engine.dispose()


def test_interrupted_read_retries_only_the_failed_page():
    calls, releases = [], []
    def execute(query):
        calls.append(query)
        if len(calls) == 1:
            raise OperationalError('read', {}, Exception('lost'), connection_invalidated=True)
        return result([{'ok': 1}])
    repository = GeoespacialRepository(SimpleNamespace(execute=execute, rollback=lambda: releases.append(1)))
    assert repository._read(text('SELECT 1')) == [{'ok': 1}]
    assert len(calls) == len(releases) == 2


def test_session_summary_preserves_labels_dates_and_empty_completed_sessions():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE etl_execution (
                execution_id CHAR(32) PRIMARY KEY, sesion_label INTEGER,
                filename TEXT, processing_date DATETIME, records_valid INTEGER, status TEXT
            )
        """))
        connection.execute(text("""
            CREATE TABLE handover_record (execution_id CHAR(32), timestamp_medicion DATETIME)
        """))
        for number, status in [(1, "completed"), (2, "completed"), (3, "failed")]:
            connection.execute(text("""
                INSERT INTO etl_execution VALUES (:id, :label, 'Session.csv', '2026-05-05 13:00:00', 0, :status)
            """), {"id": UUID(int=number).hex, "label": number + 10, "status": status})
        connection.execute(text("""
            INSERT INTO handover_record VALUES
            (:id, '2026-05-05 13:00:00'), (:id, '2026-05-05 14:00:00')
        """), {"id": UUID(int=1).hex})

    with Session(engine) as session:
        rows = GeoespacialRepository(session).executions()

    assert [row["execution_id"] for row in rows] == [UUID(int=1), UUID(int=2)]
    assert [row["sesion_label"] for row in rows] == [11, 12]
    assert rows[0]["filename"] == "Session.csv"
    assert rows[0]["fecha_inicio"] == datetime(2026, 5, 5, 13)
    assert rows[0]["fecha_fin"] == datetime(2026, 5, 5, 14)
    assert rows[1]["fecha_inicio"] is None
    assert rows[1]["fecha_fin"] is None
    engine.dispose()
