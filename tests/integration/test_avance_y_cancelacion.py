"""Puntos 3-5 contra Postgres: avance y latido, cancelación cooperativa,
verificación posterior al Load y ejecuciones interrumpidas.

Requieren las migraciones 010 y 011. Nada se confirma: cada test corre en
una transacción que termina en rollback (no quedan filas ni se consumen
números de sesión; lo verifica `counter_untouched`).
"""

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.shared.config import Settings, settings as app_settings
from app.shared.exceptions import FileValidationError, IngestionCancelled
from app.modules.ingesta.monitor import ExecutionMonitor
from app.modules.ingesta.repository import HandoverRepository, write_heartbeat
from app.modules.ingesta.schemas import ProcessRequest
from app.modules.ingesta.services import (
    MENSAJE_INTERRUMPIDA,
    execute_ingestion,
    expire_stale_executions,
    request_cancellation,
    start_ingestion,
)

from tests.integration.conftest import test_engine as engine  # noqa: E402


def _counter() -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT ultimo FROM etl_sesion_contador WHERE id = 1")).scalar()


@pytest.fixture(scope="module", autouse=True)
def counter_untouched():
    before = _counter()
    yield
    assert _counter() == before


@pytest.fixture
def connection():
    connection = engine.connect()
    transaction = connection.begin()
    yield connection
    transaction.rollback()
    connection.close()


@pytest.fixture
def db_session(connection):
    session = Session(bind=connection)
    yield session
    session.close()


@pytest.fixture
def repository(db_session):
    return HandoverRepository(db_session)


class _SameTransaction:
    """Conexión del monitor para tests: la misma transacción de prueba (la
    ejecución no está confirmada, así que una conexión aparte no la vería).
    Que en producción el monitor use otra conexión sin bloquearse lo cubre
    `test_heartbeat_from_another_connection_is_not_blocked_by_load`."""

    def __init__(self, connection):
        self._connection = connection

    def execute(self, *args, **kwargs):
        return self._connection.execute(*args, **kwargs)

    def close(self):
        pass


def _name() -> str:
    return f"Session_test_{uuid.uuid4().hex[:10]}.csv"


def _row(db_session, execution_id, columns: str):
    return db_session.execute(
        text(f"SELECT {columns} FROM etl_execution WHERE execution_id = :e"), {"e": str(execution_id)}
    ).one()


def _count(db_session, table, execution_id) -> int:
    return db_session.execute(
        text(f"SELECT COUNT(*) FROM {table} WHERE execution_id = :e"), {"e": str(execution_id)}
    ).scalar()


def _request_cancel(connection, execution_id) -> None:
    """El usuario pulsa Cancelar (lo que hace POST /cancel), sobre la conexión
    de prueba y sin pasar por una sesión, para no cruzar savepoints."""
    connection.execute(
        text("UPDATE etl_execution SET cancel_requested = true WHERE execution_id = :e AND status = 'processing'"),
        {"e": str(execution_id)},
    )


def _run(tmp_path, connection, db_session, repository, content, monitor_class=ExecutionMonitor, **settings_kwargs):
    """start_ingestion + execute_ingestion con un monitor real ligado a la
    transacción de prueba. Devuelve (execution_id, ruta del archivo temporal,
    nombre original, etapas escritas)."""
    config = Settings(
        data_input_dir=tmp_path / "input", heartbeat_min_interval_seconds=0, **settings_kwargs
    )
    filename = _name()
    stored = config.resolved_data_input_dir() / f"{uuid.uuid4()}_{filename}"
    stored.write_bytes(content)
    payload = ProcessRequest(stored_filename=stored.name, original_filename=filename)
    result = start_ingestion(payload, config, repository)
    execution_id = uuid.UUID(result.execution_id)
    written = []

    class Recording(monitor_class):
        def _beat(self, etapa, progreso, force):
            written.append((etapa, progreso))
            super()._beat(etapa, progreso, force)

    execute_ingestion(
        execution_id,
        payload,
        config,
        session_factory=lambda: Session(bind=connection, join_transaction_mode="create_savepoint"),
        monitor_factory=lambda eid, cfg: Recording(
            eid, lambda: _SameTransaction(connection), cfg.heartbeat_min_interval_seconds
        ),
    )
    db_session.expire_all()
    return execution_id, stored, filename, written


# --- Punto 3: etapa, avance y latido ------------------------------------------------


def test_stage_and_progress_are_written_and_completed_ends_at_100(
    tmp_path, connection, db_session, repository, sample_handover_csv_bytes
):
    execution_id, stored, _, written = _run(tmp_path, connection, db_session, repository, sample_handover_csv_bytes)

    assert [etapa for etapa, _ in written if etapa != "load"] == [
        "extract", "validate", "clean", "normalize", "structure", "verify",
    ]
    assert [p for _, p in written] == sorted(p for _, p in written)  # el avance nunca retrocede
    status, etapa, progreso, sesion_label = _row(db_session, execution_id, "status, etapa, progreso, sesion_label")
    assert (status, etapa, progreso) == ("completed", "done", 100)
    assert sesion_label is not None
    assert not stored.exists()  # el temporal se borra al terminar


def test_heartbeat_updates_stage_progress_and_timestamp(db_session, repository):
    execution_id = repository.create_execution(_name())
    db_session.execute(
        text("UPDATE etl_execution SET updated_at = now() - interval '5 minutes' WHERE execution_id = :e"),
        {"e": str(execution_id)},
    )

    cancel = write_heartbeat(db_session.connection(), execution_id, "load", 70)

    assert cancel is False
    etapa, progreso, reciente = _row(
        db_session, execution_id, "etapa, progreso, updated_at > now() - interval '1 minute'"
    )
    assert (etapa, progreso, reciente) == ("load", 70, True)


def test_heartbeat_from_another_connection_is_not_blocked_by_load():
    """Mientras una transacción (el Load) tiene filas insertadas con FK a una
    ejecución, otra conexión puede actualizar sus columnas de avance/latido
    sin esperar. Usa una ejecución ya existente; ambas conexiones terminan en
    rollback."""
    with engine.connect() as load, engine.connect() as side:
        execution_id = load.execute(text("SELECT execution_id FROM etl_execution LIMIT 1")).scalar()
        load.rollback()
        if execution_id is None:
            pytest.skip("No hay ninguna ejecución confirmada en la base")

        load.begin()
        load.execute(
            text(
                "INSERT INTO handover_record (execution_id, timestamp_medicion, cell_id, tecnologia, "
                "archivo_origen, origen_formato) SELECT :e, now(), 1, 1, 'prueba_lock.csv', 'csv' "
                "FROM generate_series(1, 100)"
            ),
            {"e": execution_id},
        )

        side.begin()
        side.execute(text("SET LOCAL lock_timeout = '2s'"))
        updated = side.execute(
            text(
                "UPDATE etl_execution SET etapa = etapa, progreso = progreso, updated_at = updated_at "
                "WHERE execution_id = :e"
            ),
            {"e": execution_id},
        ).rowcount  # con bloqueo, lock_timeout lanzaría OperationalError
        invisible = side.execute(
            text("SELECT COUNT(*) FROM handover_record WHERE archivo_origen = 'prueba_lock.csv'")
        ).scalar()
        side.rollback()
        load.rollback()

    assert updated == 1
    assert invisible == 0  # nadie ve la sesión a medias


# --- Punto 4: cancelación -----------------------------------------------------------


def test_cancel_during_load_leaves_no_rows_no_number_and_frees_the_name(
    tmp_path, connection, db_session, repository, sample_handover_csv_bytes
):
    class CancelAfterFirstBatch(ExecutionMonitor):
        """El usuario pulsa Cancelar cuando el primer lote ya está insertado."""

        requested = False

        def load_progress(self, sent, total):
            if not self.requested:
                type(self).requested = True
                _request_cancel(connection, self._execution_id)
            super().load_progress(sent, total)

    execution_id, stored, filename, written = _run(
        tmp_path, connection, db_session, repository, sample_handover_csv_bytes,
        monitor_class=CancelAfterFirstBatch, load_batch_rows=1,
    )

    assert written[-1][0] == "load"  # se detuvo entre lotes, no llegó a verify
    status, sesion_label, records_valid, errors = _row(
        db_session, execution_id, "status, sesion_label, records_valid, errors"
    )
    assert (status, sesion_label, records_valid, errors) == ("cancelled", None, 0, [])
    assert _count(db_session, "handover_record", execution_id) == 0
    assert _count(db_session, "handover_record_rejected", execution_id) == 0
    assert not stored.exists()
    assert repository.find_active_execution_by_filename(filename) is None
    repository.create_execution(filename)  # el nombre quedó libre: no lanza DuplicateFileError


def test_cancel_between_stages_stops_before_loading(
    tmp_path, connection, db_session, repository, sample_handover_csv_bytes
):
    class CancelAtClean(ExecutionMonitor):
        def stage(self, etapa):
            if etapa == "clean":
                _request_cancel(connection, self._execution_id)
            super().stage(etapa)

    execution_id, _, _, written = _run(
        tmp_path, connection, db_session, repository, sample_handover_csv_bytes, monitor_class=CancelAtClean
    )

    assert [etapa for etapa, _ in written] == ["extract", "validate", "clean"]
    assert _row(db_session, execution_id, "status")[0] == "cancelled"
    assert _count(db_session, "handover_record", execution_id) == 0


def test_cancel_just_before_commit_wins_over_completion(repository):
    execution_id = repository.create_execution(_name())
    repository.request_cancel(execution_id)

    with pytest.raises(IngestionCancelled):
        repository.finish_execution(
            execution_id, records_read=1, records_valid=1, records_rejected=0,
            warnings=[], errors=[], processing_time_seconds=0.1,
        )


def test_request_cancellation_outcomes(db_session, repository):
    config = Settings(stale_execution_minutes=10)

    assert request_cancellation(uuid.uuid4(), repository, config) is None  # no existe -> 404

    running = repository.create_execution(_name())
    response = request_cancellation(running, repository, config)
    assert response.status == "cancelling"
    assert _row(db_session, running, "status, cancel_requested") == ("processing", True)

    completed = repository.create_execution(_name())
    repository.finish_execution(
        completed, records_read=0, records_valid=0, records_rejected=0,
        warnings=[], errors=[], processing_time_seconds=0.1,
    )
    with pytest.raises(FileValidationError, match="ya está completada"):  # -> 409, no deshace nada
        request_cancellation(completed, repository, config)
    db_session.expire_all()
    assert _row(db_session, completed, "status")[0] == "completed"


def test_cancelling_an_execution_without_heartbeat_closes_it_immediately(db_session, repository):
    execution_id = repository.create_execution(_name())
    db_session.execute(
        text("UPDATE etl_execution SET updated_at = now() - interval '11 minutes' WHERE execution_id = :e"),
        {"e": str(execution_id)},
    )
    db_session.expire_all()

    response = request_cancellation(execution_id, repository, Settings(stale_execution_minutes=10))

    assert response.status == "cancelled"
    assert _row(db_session, execution_id, "status, sesion_label") == ("cancelled", None)


# --- Punto 5: verificación post-Load y ejecuciones interrumpidas ----------------------


def test_post_load_count_mismatch_rolls_back_and_marks_failed(
    tmp_path, connection, db_session, repository, sample_handover_csv_bytes, monkeypatch
):
    monkeypatch.setattr(HandoverRepository, "count_records", lambda self, execution_id: (1, 0))

    execution_id, stored, _, _ = _run(tmp_path, connection, db_session, repository, sample_handover_csv_bytes)

    status, errors, sesion_label = _row(db_session, execution_id, "status, errors, sesion_label")
    assert status == "failed"
    assert "verificación posterior a la carga no coincidió" in errors[0]
    assert sesion_label is None
    assert _count(db_session, "handover_record", execution_id) == 0
    assert _count(db_session, "handover_record_rejected", execution_id) == 0
    assert not stored.exists()


def test_execution_without_heartbeat_is_marked_interrupted_and_fresh_one_is_not(db_session, repository):
    config = Settings(stale_execution_minutes=10)
    stale, fresh = repository.create_execution(_name()), repository.create_execution(_name())
    db_session.execute(
        text("UPDATE etl_execution SET updated_at = now() - interval '11 minutes' WHERE execution_id = :e"),
        {"e": str(stale)},
    )

    assert expire_stale_executions(repository, config, stale) == 1
    assert expire_stale_executions(repository, config, fresh) == 0

    status, errors = _row(db_session, stale, "status, errors")
    assert (status, errors) == ("failed", [MENSAJE_INTERRUMPIDA])
    assert _row(db_session, fresh, "status")[0] == "processing"
    assert repository.find_active_execution_by_filename(
        _row(db_session, stale, "filename")[0]
    ) is None  # el nombre queda libre


def test_real_monitor_uses_a_separate_autocommit_connection():
    """El monitor de producción (conexión propia, AUTOCOMMIT) contra la base
    real, sin escribir nada: para un execution_id inexistente el UPDATE no
    toca filas y el monitor detiene el pipeline (la ejecución "ya no está en
    processing")."""
    from app.modules.ingesta.monitor import default_monitor

    monitor = default_monitor(uuid.uuid4(), Settings())
    try:
        with pytest.raises(IngestionCancelled):
            monitor.stage("extract")
        # Autocommit real en el driver: lo que escribe queda visible de
        # inmediato para GET /status, sin esperar a ningún commit.
        assert monitor._connection.connection.driver_connection.autocommit is True
    finally:
        monitor.close()
