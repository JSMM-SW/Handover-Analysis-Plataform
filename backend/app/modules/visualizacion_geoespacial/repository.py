from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.shared.db.models import EtlExecution, HandoverRecord


class GeoespacialRepository:
    def __init__(self, db: Session):
        self.db = db

    def executions(self):
        return [dict(execution_id=row.execution_id, sesion_label=row.sesion_label, filename=row.filename,
                     processing_date=row.processing_date, records_valid=row.records_valid,
                     status=row.status, fecha_inicio=row.fecha_inicio, fecha_fin=row.fecha_fin)
                for row in self.db.execute(
            select(EtlExecution.execution_id, EtlExecution.sesion_label, EtlExecution.filename, EtlExecution.processing_date,
                   EtlExecution.records_valid, EtlExecution.status,
                   func.min(HandoverRecord.timestamp_medicion).label("fecha_inicio"),
                   func.max(HandoverRecord.timestamp_medicion).label("fecha_fin"))
            .outerjoin(HandoverRecord, HandoverRecord.execution_id == EtlExecution.execution_id)
            .where(EtlExecution.status == "completed")
            .group_by(EtlExecution.execution_id)
            .order_by(EtlExecution.processing_date.desc(), EtlExecution.execution_id)
        ).all()]

    def execution(self, execution_id):
        return self.db.get(EtlExecution, execution_id)

    def sheets(self, execution_id):
        return self.db.scalars(
            select(HandoverRecord.hoja_origen)
            .where(HandoverRecord.execution_id == execution_id)
            .distinct().order_by(HandoverRecord.hoja_origen)
        ).all()

    def measurements(self, execution_ids, hoja, desde=None, hasta=None):
        query = select(HandoverRecord).where(
            HandoverRecord.execution_id.in_(execution_ids),
        )
        if hoja is not None:
            query = query.where(HandoverRecord.hoja_origen == hoja)
        if desde is not None:
            # Context before the visible interval preserves events at its boundary.
            query = query.where(HandoverRecord.timestamp_medicion >= desde - timedelta(seconds=60))
        if hasta is not None:
            query = query.where(HandoverRecord.timestamp_medicion <= hasta)
        # One extra row detects overflow; the API rejects rather than truncates a route.
        return self.db.scalars(query.order_by(
            HandoverRecord.execution_id, HandoverRecord.hoja_origen,
            HandoverRecord.timestamp_medicion, HandoverRecord.id_registro,
        ).limit(20001)).all()
