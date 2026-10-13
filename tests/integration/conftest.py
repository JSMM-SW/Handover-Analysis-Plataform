"""Fixtures compartidas de los tests de integración de ingesta."""

import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.main import app
from app.shared.config import Settings, get_settings, settings
from app.shared.db.database import get_db
from app.modules.ingesta import router as ingesta_router
from app.modules.ingesta.monitor import ExecutionMonitor
from app.modules.ingesta.services import execute_ingestion


# Un único engine SIN pool para los tests de ingesta: cada conexión se cierra
# de verdad al soltarla. El pooler de Supabase en modo sesión admite 15
# clientes en total (compartidos con el backend en marcha y con el equipo);
# un engine con pool por archivo o por test los agota.
test_engine = create_engine(settings.database_url, poolclass=NullPool)


@dataclass
class RollbackApp:
    client: TestClient
    connection: Connection  # consultar con esta conexión: ve lo no confirmado del test
    settings: Settings


class _SameTransaction:
    """Conexión del monitor de avance dentro de la transacción de prueba."""

    def __init__(self, connection):
        self._connection = connection

    def execute(self, *args, **kwargs):
        return self._connection.execute(*args, **kwargs)

    def close(self):
        pass


@pytest.fixture
def rollback_app(tmp_path, monkeypatch):
    """La app completa por HTTP (/upload, /process, /status, /cancel, /export),
    con TODO su acceso a la base dentro de una única transacción que se
    revierte al final: nada queda en la base compartida, ningún otro módulo ve
    la sesión de prueba y no se consume número de sesión. Los archivos
    temporales van a una carpeta temporal, no a data/input/.

    Cada request recibe una sesión en modo SAVEPOINT sobre la misma conexión;
    la carga en segundo plano (execute_ingestion) usa esa misma conexión para
    sus datos y para el monitor de avance.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    config = Settings(data_input_dir=tmp_path / "input", heartbeat_min_interval_seconds=0)

    def session_factory():
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    def override_get_db():
        db = session_factory()
        try:
            yield db
            # La sesión de la request puede seguir con un SAVEPOINT abierto
            # mientras corre la tarea en segundo plano (que anida el suyo en
            # la misma conexión). Hay que LIBERARLO, no revertirlo: un
            # close() a secas lo revertiría junto con todo lo anidado. (En
            # producción cada parte usa su propia conexión.)
            db.commit()
        finally:
            db.close()

    def execute_in_test_transaction(execution_id, payload, request_settings):
        execute_ingestion(
            execution_id,
            payload,
            request_settings,
            session_factory=session_factory,
            monitor_factory=lambda eid, cfg: ExecutionMonitor(
                eid, lambda: _SameTransaction(connection), cfg.heartbeat_min_interval_seconds
            ),
        )

    monkeypatch.setattr(ingesta_router, "execute_ingestion", execute_in_test_transaction)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: config
    try:
        with TestClient(app) as client:
            yield RollbackApp(client=client, connection=connection, settings=config)
    finally:
        app.dependency_overrides.clear()
        transaction.rollback()
        connection.close()


def unique_csv_name(prefix: str = "Session_test") -> str:
    """Nombre de archivo que no choca con sesiones reales ya cargadas (la
    carga rechaza con 409 un nombre que ya tiene una ejecución completed)."""
    return f"{prefix}_{uuid.uuid4().hex[:10]}.csv"
