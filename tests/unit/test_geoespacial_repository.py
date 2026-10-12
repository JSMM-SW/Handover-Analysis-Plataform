"""Exercise the session summary query without connecting to the shared database."""
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.modules.visualizacion_geoespacial.repository import GeoespacialRepository
from app.modules.visualizacion_temporal.detector import Medicion


def test_availability_merges_adjacent_minutes_but_preserves_gaps_and_days():
    rows = [{'minuto': datetime(2026, 5, 5, 8, 0), 'n_mediciones': 2},
            {'minuto': datetime(2026, 5, 5, 8, 1), 'n_mediciones': 3},
            {'minuto': datetime(2026, 5, 5, 10, 0), 'n_mediciones': 1},
            {'minuto': datetime(2026, 5, 6, 11, 0), 'n_mediciones': 4}]
    db = SimpleNamespace(execute=lambda query: SimpleNamespace(mappings=lambda: rows))
    assert GeoespacialRepository(db).available_days([UUID(int=1)]) == [
        {'fecha': '2026-05-05', 'n_mediciones': 6, 'franjas': [
            {'inicio': '08:00', 'fin': '08:01'}, {'inicio': '10:00', 'fin': '10:00'}]},
        {'fecha': '2026-05-06', 'n_mediciones': 4, 'franjas': [{'inicio': '11:00', 'fin': '11:00'}]},
    ]


def test_handovers_use_temporal_measurements_from_complete_independent_sessions(monkeypatch):
    calls = []

    def measurements(self, session_id, desde=None, hasta=None):
        calls.append((session_id, desde, hasta))
        return [Medicion(id_medicion=str(UUID(int=index + 1)), sesion_id=session_id,
                         timestamp_medicion=datetime(2026, 5, 5, 8, 0, index),
                         cid=10 if index < 2 else 20, node_id=100, tech='LTE') for index in range(4)]

    monkeypatch.setattr('app.modules.visualizacion_geoespacial.repository.VisualizacionTemporalRepository.obtener_mediciones', measurements)
    sessions = [UUID(int=100), UUID(int=200)]
    events = GeoespacialRepository(None).handovers(sessions)
    assert calls == [(str(session), None, None) for session in sessions]
    assert len(events) == 2
    assert {event.sesion_id for event in events} == {str(session) for session in sessions}


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
