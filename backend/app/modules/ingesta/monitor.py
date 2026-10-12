"""Avance, latido y cancelación cooperativa de una ejecución en curso.

Todo se escribe y se lee por una conexión APARTE de la transacción del Load,
en autocommit: GET /status ve la etapa y el avance al instante (no al commit
del Load) y la bandera de cancelación que se lee es la ya confirmada por
POST /cancel. Las escrituras son pocas: una por cambio de etapa y, dentro de
una etapa (lotes de COPY), como mucho una cada `min_interval_seconds`.
"""

import logging
import time
import uuid
from typing import Callable

from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from app.shared.config import Settings
from app.shared.exceptions import IngestionCancelled
from app.modules.ingesta.repository import write_heartbeat

logger = logging.getLogger(__name__)

# Avance (0-100) al ENTRAR a cada etapa. El Load reparte 55-95 según las
# filas ya enviadas; "done" (100) lo escribe finish_execution con el commit.
STAGE_PROGRESS = {
    "extract": 5,
    "validate": 25,
    "clean": 35,
    "normalize": 40,
    "structure": 50,
    "load": 55,
    "verify": 97,
}
LOAD_PROGRESS_START = STAGE_PROGRESS["load"]
LOAD_PROGRESS_END = 95


class ExecutionMonitor:
    def __init__(
        self,
        execution_id: uuid.UUID,
        connect: Callable[[], Connection],
        min_interval_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._execution_id = execution_id
        self._connect = connect
        self._min_interval = min_interval_seconds
        self._clock = clock
        self._connection: Connection | None = None
        self._last_beat: float | None = None

    def stage(self, etapa: str) -> None:
        """Cambio de etapa: siempre se escribe (y se revisa la cancelación)."""
        self._beat(etapa, STAGE_PROGRESS.get(etapa, 0), force=True)

    def load_progress(self, sent: int, total: int) -> None:
        """Después de cada lote de COPY: avance del Load. Se escribe como
        mucho una vez cada `min_interval_seconds`."""
        fraction = sent / total if total else 1.0
        progreso = LOAD_PROGRESS_START + int((LOAD_PROGRESS_END - LOAD_PROGRESS_START) * fraction)
        self._beat("load", progreso, force=False)

    def _beat(self, etapa: str, progreso: int, force: bool) -> None:
        now = self._clock()
        if not force and self._last_beat is not None and now - self._last_beat < self._min_interval:
            return
        self._last_beat = now
        try:
            if self._connection is None:
                self._connection = self._connect()
            cancel_requested = write_heartbeat(self._connection, self._execution_id, etapa, progreso)
        except DBAPIError as exc:
            # Un latido perdido no debe tumbar la carga: se reintenta en el
            # siguiente con una conexión nueva.
            logger.warning("[%s] No se pudo escribir el avance (%s): %s", self._execution_id, etapa, exc)
            self.close()
            return
        if cancel_requested is None or cancel_requested:
            # None: la ejecución ya no está en "processing" (cancelada o
            # marcada como interrumpida desde fuera): también se detiene.
            raise IngestionCancelled()

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except DBAPIError:
                pass
            self._connection = None


def default_monitor(execution_id: uuid.UUID, settings: Settings) -> ExecutionMonitor:
    from app.shared.db.database import engine

    return ExecutionMonitor(
        execution_id,
        lambda: engine.connect().execution_options(isolation_level="AUTOCOMMIT"),
        settings.heartbeat_min_interval_seconds,
    )
