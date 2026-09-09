from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared.db.models import EtlExecution, HandoverRecord


class GeoespacialRepository:
    def __init__(self, db: Session):
        self.db = db

    def executions(self):
        return self.db.scalars(
            select(EtlExecution)
            .where(EtlExecution.status == "completed")
            .order_by(EtlExecution.processing_date.desc(), EtlExecution.execution_id)
        ).all()

    def execution(self, execution_id):
        return self.db.get(EtlExecution, execution_id)

    def sheets(self, execution_id):
        return self.db.scalars(
            select(HandoverRecord.hoja_origen)
            .where(HandoverRecord.execution_id == execution_id)
            .distinct().order_by(HandoverRecord.hoja_origen)
        ).all()

    def measurements(self, execution_id, hoja, desde=None, hasta=None):
        query = select(HandoverRecord).where(
            HandoverRecord.execution_id == execution_id,
            HandoverRecord.hoja_origen == hoja,
        )
        if desde is not None:
            query = query.where(HandoverRecord.timestamp_medicion >= desde)
        if hasta is not None:
            query = query.where(HandoverRecord.timestamp_medicion <= hasta)
        # One extra row detects overflow; the API rejects rather than truncates a route.
        return self.db.scalars(query.order_by(
            HandoverRecord.timestamp_medicion, HandoverRecord.id_registro,
        ).limit(20001)).all()
