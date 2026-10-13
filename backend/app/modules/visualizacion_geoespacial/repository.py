from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.shared.db.models import EtlExecution, HandoverRecord
from app.modules.visualizacion_temporal.repository import VisualizacionTemporalRepository
from app.modules.visualizacion_temporal.detector import detectar_handovers
from .constants import MAX_CONTINUITY_SECONDS, MAX_MEASUREMENTS


class GeoespacialRepository:
    def __init__(self, db: Session):
        self.db = db

    def executions(self):
        query = (
            select(
                EtlExecution.execution_id,
                EtlExecution.sesion_label,
                EtlExecution.filename,
                EtlExecution.processing_date,
                EtlExecution.records_valid,
                EtlExecution.status,
                func.min(HandoverRecord.timestamp_medicion).label("fecha_inicio"),
                func.max(HandoverRecord.timestamp_medicion).label("fecha_fin"),
            )
            .outerjoin(HandoverRecord, HandoverRecord.execution_id == EtlExecution.execution_id)
            .where(EtlExecution.status == "completed")
            .group_by(EtlExecution.execution_id)
            .order_by(EtlExecution.processing_date.desc(), EtlExecution.execution_id)
        )
        return [dict(row) for row in self.db.execute(query).mappings()]

    def execution(self, execution_id):
        return self.db.get(EtlExecution, execution_id)

    def handovers(self, execution_ids):
        # Detect on complete sessions before visual filters; do not depend on
        # a prior visit to Temporal or mutate its stored events.
        temporal = VisualizacionTemporalRepository(self.db)
        events = []
        for execution_id in execution_ids:
            events.extend(detectar_handovers(temporal.obtener_mediciones(str(execution_id))))
        return events

    def available_days(self, execution_ids):
        local_timestamp = func.timezone('America/Guayaquil', HandoverRecord.timestamp_medicion)
        local_minute = func.date_trunc('minute', local_timestamp)
        query = (select(local_minute.label('minuto'), func.count().label('n_mediciones'))
                 .where(HandoverRecord.execution_id.in_(execution_ids))
                 .group_by(local_minute).order_by(local_minute))
        days = {}
        for row in self.db.execute(query).mappings():
            minute = row['minuto']
            day = days.setdefault(minute.date().isoformat(), {'fecha': minute.date().isoformat(),
                                                            'n_mediciones': 0, 'franjas': []})
            day['n_mediciones'] += row['n_mediciones']
            hour = minute.strftime('%H:%M')
            ranges = day['franjas']
            if ranges and minute - timedelta(minutes=1) == ranges[-1]['last']:
                ranges[-1]['fin'] = hour
                ranges[-1]['last'] = minute
            else:
                ranges.append({'inicio': hour, 'fin': hour, 'last': minute})
        for day in days.values():
            for interval in day['franjas']:
                interval.pop('last')
        return list(days.values())

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
            query = query.where(HandoverRecord.timestamp_medicion >= desde - timedelta(seconds=MAX_CONTINUITY_SECONDS))
        if hasta is not None:
            query = query.where(HandoverRecord.timestamp_medicion <= hasta)
        # One extra row detects overflow; the API rejects rather than truncates a route.
        return self.db.scalars(query.order_by(
            HandoverRecord.execution_id, HandoverRecord.hoja_origen,
            HandoverRecord.timestamp_medicion, HandoverRecord.id_registro,
        ).limit(MAX_MEASUREMENTS + 1)).all()
