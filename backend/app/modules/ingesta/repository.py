"""
Repository Pattern para el módulo ETL de handovers.

Este es el único punto del sistema que debe contener sentencias de acceso a
datos (SQLAlchemy). Las etapas del pipeline ETL (Extract/Validate/Clean/
Normalize/Structure) NUNCA deben importar SQLAlchemy directamente ni construir
queries: solo entregan diccionarios a estos métodos. Así, la lógica de negocio
y transformación no queda acoplada al motor de base de datos (sección 11 del
plan de tesis).
"""

import json
import uuid
from datetime import datetime, timezone
from itertools import islice
from typing import Callable, Iterable, Sequence

from sqlalchemy import func, select, text, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.shared.db.models import EtlExecution, HandoverRecord, HandoverRecordRejected
from app.shared.exceptions import DuplicateFileError, IngestionCancelled

# Estados que bloquean volver a cargar el mismo nombre de archivo. "failed"
# (y "cancelled") no bloquean: si no, una subida fallida bloquearía el
# nombre para siempre.
ACTIVE_STATUSES = ("processing", "completed")

# Índice único parcial sobre filename_clave (ver schema.sql).
UX_FILENAME_ACTIVO = "ux_etl_execution_filename_activo"

# Filas por sentencia COPY si quien construye el repositorio no indica otro
# valor (la aplicación pasa settings.load_batch_rows).
DEFAULT_LOAD_BATCH_ROWS = 50_000


def write_heartbeat(
    connection: Connection, execution_id: uuid.UUID, etapa: str, progreso: int
) -> bool | None:
    """Escribe etapa, progreso y latido (updated_at) de una ejecución en
    "processing" y devuelve su bandera `cancel_requested`, en una sola
    sentencia. Devuelve None si la ejecución ya no está en "processing".

    `connection` debe ser una conexión APARTE de la transacción del Load y en
    autocommit: así GET /status ve el avance al instante y la bandera leída es
    la ya confirmada por POST /cancel. No se bloquea con las filas que el Load
    tiene insertadas con FK a la ejecución (verificado: el Load toma FOR KEY
    SHARE; este UPDATE no toca columnas clave).
    """
    return connection.execute(
        update(EtlExecution)
        .where(EtlExecution.execution_id == execution_id, EtlExecution.status == "processing")
        .values(etapa=etapa, progreso=progreso, updated_at=func.now())
        .returning(EtlExecution.cancel_requested)
    ).scalar_one_or_none()


class HandoverRepository:
    def __init__(self, db: Session, load_batch_rows: int = DEFAULT_LOAD_BATCH_ROWS):
        self._db = db
        self._load_batch_rows = max(1, load_batch_rows)

    def ping(self) -> None:
        """Consulta mínima para comprobar que la conexión responde (segura de
        reintentar: no modifica nada)."""
        self._db.execute(text("SELECT 1"))

    def get_execution(self, execution_id: uuid.UUID) -> EtlExecution | None:
        """Lee el estado persistido de una ejecución (GET /ingestion/status/{id})."""
        return self._db.get(EtlExecution, execution_id)

    def get_execution_id_by_sesion_label(self, sesion_label: int) -> uuid.UUID | None:
        """Resuelve el identificador corto y amigable (sesion_label) al
        execution_id real. Usado por GET /ingestion/export?sesion_label=.
        """
        execution = (
            self._db.query(EtlExecution)
            .filter(EtlExecution.sesion_label == sesion_label)
            .one_or_none()
        )
        return execution.execution_id if execution else None

    def get_valid_records(self, execution_id: uuid.UUID | None = None) -> list[HandoverRecord]:
        """Lee el dataset limpio (handover_record), nunca handover_record_rejected.

        Sin `execution_id`, devuelve el dataset completo (todas las
        ejecuciones); con él, solo los registros de esa ejecución. Usado por
        GET /ingestion/export.
        """
        query = self._db.query(HandoverRecord)
        if execution_id is not None:
            query = query.filter(HandoverRecord.execution_id == execution_id)
        return query.order_by(HandoverRecord.timestamp_medicion).all()

    def find_active_execution_by_filename(self, filename: str) -> EtlExecution | None:
        """Ejecución "processing" o "completed" cuyo nombre original
        normalizado coincide con el de `filename` (la más reciente), o None.

        La normalización se calcula en Postgres con la misma expresión que
        la columna generada `filename_clave`, para que la búsqueda y el
        índice único parcial nunca discrepen.
        """
        clave = func.lower(func.btrim(func.regexp_replace(filename, r"^.*[\\/]", "")))
        return (
            self._db.query(EtlExecution)
            .filter(
                EtlExecution.filename_clave == clave,
                EtlExecution.status.in_(ACTIVE_STATUSES),
            )
            .order_by(EtlExecution.processing_date.desc())
            .first()
        )

    def create_execution(self, filename: str, stored_filename: str | None = None) -> uuid.UUID:
        """Crea la fila de trazabilidad al iniciar el procesamiento de un archivo.
        `stored_filename` es el temporal en data/input/ (para poder borrarlo
        al terminar, fallar o cancelar).

        Si otra ejecución "processing"/"completed" ya tiene el mismo nombre
        normalizado (subidas simultáneas que pasaron el chequeo previo), el
        índice único parcial rechaza el INSERT y se lanza DuplicateFileError.
        """
        execution = EtlExecution(
            filename=filename,
            status="processing",
            stored_filename=stored_filename,
            etapa="en_cola",
            progreso=0,
        )
        self._db.add(execution)
        try:
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == UX_FILENAME_ACTIVO:
                raise DuplicateFileError(filename) from exc
            raise
        self._db.refresh(execution)
        return execution.execution_id

    def _copy_rows(
        self, table, rows: Iterable[tuple], on_batch: Callable[[int], None] | None = None
    ) -> None:
        """Inserta `rows` (una tupla por fila, en el orden de las columnas de
        `table`) con COPY FROM STDIN de psycopg 3.

        Usa la conexión de la propia sesión, así que participa en su
        transacción (commit/rollback) igual que un INSERT del ORM. Reemplaza
        a `bulk_save_objects`, que mandaba un INSERT por fila: medido contra
        Supabase, ~154 filas/s (86k filas ≈ 9 min) frente a ~15,000 filas/s.

        Las filas se envían en tandas de `load_batch_rows`, una sentencia
        COPY por tanda y todas en la MISMA transacción: ninguna sentencia se
        acerca al statement_timeout del servidor por grande que sea el
        archivo. `on_batch(filas_enviadas)` se llama después de cada tanda
        (avance, latido, cancelación); si lanza una excepción, la carga se
        interrumpe y quien llama hace rollback.
        """
        columns = ", ".join(f'"{column.name}"' for column in table.columns)
        statement = f"COPY {table.name} ({columns}) FROM STDIN"
        raw_connection = self._db.connection().connection.driver_connection
        iterator = iter(rows)
        sent = 0
        with raw_connection.cursor() as cursor:
            while batch := list(islice(iterator, self._load_batch_rows)):
                with cursor.copy(statement) as copy:
                    for row in batch:
                        copy.write_row(row)
                sent += len(batch)
                if on_batch is not None:
                    on_batch(sent)

    def save_valid_records(
        self,
        execution_id: uuid.UUID,
        records: Sequence[dict],
        on_batch: Callable[[int], None] | None = None,
    ) -> None:
        """Inserta en lote los registros que ya pasaron Validate/Clean/Normalize.

        Cada dict debe traer las claves de HandoverRecord (timestamp_medicion,
        cell_id, tac, earfcn, tecnologia, latitud, longitud, rsrp,
        node_id, psc_pci, rssi, rsrq, rssnr, accuracy, archivo_origen,
        hoja_origen, origen_formato). Las medidas ausentes se guardan como None.
        No hace commit: lo hace `finish_execution`, para que los registros y el
        estado final de la ejecución se confirmen juntos (o no se confirmen).
        """
        if not records:
            return
        table = HandoverRecord.__table__
        now = datetime.now(timezone.utc)
        generated = {"execution_id": execution_id, "created_at": now}

        def rows():
            for record in records:
                values = {**record, **generated, "id_registro": uuid.uuid4()}
                yield tuple(values.get(column.name) for column in table.columns)

        self._copy_rows(table, rows(), on_batch)

    def save_rejected_records(
        self,
        execution_id: uuid.UUID,
        rejected: Sequence[dict],
        on_batch: Callable[[int], None] | None = None,
    ) -> None:
        """Inserta los registros descartados durante Validate/Clean.

        Cada dict debe traer al menos: motivo_rechazo, datos_crudos. Igual que
        `save_valid_records`, no hace commit.
        """
        if not rejected:
            return
        table = HandoverRecordRejected.__table__
        now = datetime.now(timezone.utc)

        def rows():
            for item in rejected:
                values = {
                    **item,
                    # default=str: valores crudos no serializables se guardan
                    # como texto en vez de romper.
                    "datos_crudos": json.dumps(item["datos_crudos"], default=str, ensure_ascii=False),
                    "execution_id": execution_id,
                    "created_at": now,
                    "id_rechazo": uuid.uuid4(),
                }
                yield tuple(values.get(column.name) for column in table.columns)

        self._copy_rows(table, rows(), on_batch)

    def finish_execution(
        self,
        execution_id: uuid.UUID,
        records_read: int,
        records_valid: int,
        records_rejected: int,
        warnings: list,
        errors: list,
        processing_time_seconds: float,
    ) -> None:
        """Actualiza la fila de trazabilidad con el resultado final del
        procesamiento y confirma la transacción: el commit incluye los
        registros que `save_valid_records`/`save_rejected_records` dejaron
        pendientes, así que ejecución y datos quedan consistentes.

        Al pasar a "completed", el trigger trg_etl_execution_sesion_label
        asigna `sesion_label` en esta misma transacción: si el commit no
        ocurre (rollback), el número no se consume."""
        if not errors:
            # Bloquea la fila hasta el commit y lee la bandera ya confirmada:
            # una cancelación que llegó justo antes gana (rollback total), y
            # una que llegue después espera al commit y recibe "ya completada".
            cancel_requested = self._db.execute(
                select(EtlExecution.cancel_requested)
                .where(EtlExecution.execution_id == execution_id)
                .with_for_update()
            ).scalar_one_or_none()
            if cancel_requested:
                raise IngestionCancelled()

        execution = self._db.get(EtlExecution, execution_id)
        if execution is None:
            raise ValueError(f"No existe la ejecución {execution_id}")

        execution.records_read = records_read
        execution.records_valid = records_valid
        execution.records_rejected = records_rejected
        execution.warnings = warnings
        execution.errors = errors
        execution.processing_time_seconds = processing_time_seconds
        execution.status = "failed" if errors else "completed"
        execution.updated_at = datetime.now(timezone.utc)
        if not errors:
            execution.etapa = "done"
            execution.progreso = 100

        self._db.commit()

    def count_records(self, execution_id: uuid.UUID) -> tuple[int, int]:
        """(filas en handover_record, filas en handover_record_rejected) de la
        ejecución, vistas desde la transacción del Load (verificación
        posterior a la carga, antes del commit)."""
        valid = self._db.execute(
            select(func.count()).select_from(HandoverRecord).where(HandoverRecord.execution_id == execution_id)
        ).scalar_one()
        rejected = self._db.execute(
            select(func.count())
            .select_from(HandoverRecordRejected)
            .where(HandoverRecordRejected.execution_id == execution_id)
        ).scalar_one()
        return valid, rejected

    def mark_cancelled(self, execution_id: uuid.UUID, processing_time_seconds: float | None = None) -> bool:
        """Deja en "cancelled" una ejecución que sigue en "processing" (sin
        registros: quien llama ya hizo rollback del Load). No asigna número
        de sesión y libera el nombre del archivo. Devuelve False si la
        ejecución ya no estaba en "processing"."""
        updated = self._db.execute(
            update(EtlExecution)
            .where(EtlExecution.execution_id == execution_id, EtlExecution.status == "processing")
            .values(
                status="cancelled",
                records_read=0,
                records_valid=0,
                records_rejected=0,
                warnings=[],
                errors=[],
                processing_time_seconds=processing_time_seconds,
                updated_at=func.now(),
            )
        ).rowcount
        self._db.commit()
        return bool(updated)

    def request_cancel(self, execution_id: uuid.UUID) -> bool:
        """Enciende la bandera de cancelación de una ejecución en
        "processing". Devuelve False si ya no estaba en "processing"."""
        updated = self._db.execute(
            update(EtlExecution)
            .where(EtlExecution.execution_id == execution_id, EtlExecution.status == "processing")
            .values(cancel_requested=True)
        ).rowcount
        self._db.commit()
        return bool(updated)

    def mark_stale_executions(
        self, stale_minutes: int, message: str, execution_id: uuid.UUID | None = None
    ) -> list[tuple[uuid.UUID, str | None]]:
        """Marca como "failed" las ejecuciones en "processing" sin latido
        (updated_at) desde hace más de `stale_minutes` (todas, o solo
        `execution_id`). Devuelve [(execution_id, stored_filename)] de las
        marcadas, para que quien llama borre sus archivos temporales."""
        conditions = [
            EtlExecution.status == "processing",
            EtlExecution.updated_at < func.now() - func.make_interval(0, 0, 0, 0, 0, stale_minutes),
        ]
        if execution_id is not None:
            conditions.append(EtlExecution.execution_id == execution_id)
        rows = self._db.execute(
            update(EtlExecution)
            .where(*conditions)
            .values(status="failed", errors=EtlExecution.errors.op("||")(func.jsonb_build_array(message)))
            .returning(EtlExecution.execution_id, EtlExecution.stored_filename)
        ).all()
        self._db.commit()
        return [(row[0], row[1]) for row in rows]

    def statuses_by_stored_filename(self, stored_filenames: Sequence[str]) -> dict[str, str]:
        """{stored_filename: status} de las ejecuciones dueñas de esos
        archivos temporales (los que no tienen ejecución no aparecen)."""
        if not stored_filenames:
            return {}
        rows = self._db.execute(
            select(EtlExecution.stored_filename, EtlExecution.status).where(
                EtlExecution.stored_filename.in_(list(stored_filenames))
            )
        ).all()
        return {row[0]: row[1] for row in rows}
