"""Exercise the session summary query without connecting to the shared database."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.modules.visualizacion_geoespacial.repository import GeoespacialRepository


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
