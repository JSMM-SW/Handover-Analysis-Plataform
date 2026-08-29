"""
Repository Pattern para el módulo ETL de handovers.

Este es el único punto del sistema que debe contener sentencias de acceso a
datos (SQLAlchemy). Las etapas del pipeline ETL (Extract/Validate/Clean/
Normalize/Structure) NUNCA deben importar SQLAlchemy directamente ni construir
queries: solo entregan diccionarios a estos métodos. Así, la lógica de negocio
y transformación no queda acoplada al motor de base de datos (sección 11 del
plan de tesis).
"""

import uuid
from typing import Sequence

from sqlalchemy.orm import Session

from app.models.handover import EtlExecution, HandoverRecord, HandoverRecordRejected


class HandoverRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_execution(self, execution_id: uuid.UUID) -> EtlExecution | None:
        """Lee el estado persistido de una ejecución (GET /ingestion/status/{id})."""
        return self._db.get(EtlExecution, execution_id)

    def create_execution(self, filename: str) -> uuid.UUID:
        """Crea la fila de trazabilidad al iniciar el procesamiento de un archivo."""
        execution = EtlExecution(filename=filename, status="processing")
        self._db.add(execution)
        self._db.commit()
        self._db.refresh(execution)
        return execution.execution_id

    def save_valid_records(self, execution_id: uuid.UUID, records: Sequence[dict]) -> None:
        """Inserta en lote los registros que ya pasaron Validate/Clean/Normalize.

        Cada dict debe traer las claves de HandoverRecord (timestamp_medicion,
        cell_id, tac, earfcn, tecnologia, latitud, longitud, rsrp_dbm,
        archivo_origen, hoja_origen).
        """
        if not records:
            return
        objects = [HandoverRecord(execution_id=execution_id, **record) for record in records]
        self._db.bulk_save_objects(objects)
        self._db.commit()

    def save_rejected_records(self, execution_id: uuid.UUID, rejected: Sequence[dict]) -> None:
        """Inserta los registros descartados durante Validate/Clean.

        Cada dict debe traer al menos: motivo_rechazo, datos_crudos.
        """
        if not rejected:
            return
        objects = [
            HandoverRecordRejected(execution_id=execution_id, **item) for item in rejected
        ]
        self._db.bulk_save_objects(objects)
        self._db.commit()

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
        """Actualiza la fila de trazabilidad con el resultado final del procesamiento."""
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

        self._db.commit()
