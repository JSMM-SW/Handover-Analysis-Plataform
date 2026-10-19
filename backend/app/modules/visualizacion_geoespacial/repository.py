from datetime import timedelta
from collections import namedtuple
from types import SimpleNamespace
import logging
from time import monotonic

from sqlalchemy import func, select, and_, or_
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.shared.db.models import EtlExecution, HandoverRecord
from app.modules.visualizacion_temporal.detector import Medicion, detectar_handovers
from .constants import MAX_CONTINUITY_SECONDS
from .analysis_cache import session_cache

logger = logging.getLogger(__name__)
READ_BATCH_SIZE = 5_000
RECORD_COLUMNS = (
    'id_registro', 'execution_id', 'timestamp_medicion', 'latitud', 'longitud',
    'cell_id', 'tecnologia', 'rsrp', 'hoja_origen', 'node_id', 'psc_pci',
    'earfcn', 'tac', 'rssi', 'rsrq', 'rssnr', 'accuracy', 'velocidad_kmh',
    'cid', 'lac_tac_raw', 'report_index', 'net_type', 'tech', 'data_state', 'call_state',
)
SessionRecord = namedtuple('SessionRecord', RECORD_COLUMNS)


def as_temporal_measurement(row):
    """Same ETL field precedence as Temporal's SQL projection; same detector."""
    return Medicion(
        id_medicion=str(row.id_registro), sesion_id=str(row.execution_id),
        timestamp_medicion=row.timestamp_medicion, report_index=row.report_index,
        cid=row.cid if row.cid is not None else row.cell_id,
        node_id=row.node_id, psc_pci=row.psc_pci,
        lac_tac=row.lac_tac_raw if row.lac_tac_raw is not None else row.tac,
        tech=row.tech if row.tech is not None else {1: 'LTE', 2: 'WCDMA', 3: 'GSM'}.get(row.tecnologia),
        net_type=row.net_type, arfcn=row.earfcn,
        rsrp_dbm=row.rsrp, rssi_dbm=row.rssi, rsrq_db=row.rsrq, rssnr_db=row.rssnr,
        data_state=row.data_state, call_state=row.call_state,
    )


class GeoespacialRepository:
    def __init__(self, db: Session):
        self.db = db
        self._session_records = {}
        self._session_events = {}
        self._session_versions = {}

    def _read(self, query):
        """Release each read transaction before Python processing or waiting."""
        for attempt in range(2):
            try:
                rows = self.db.execute(query).mappings().all()
                self.db.rollback()
                return rows
            except DBAPIError as error:
                try:
                    self.db.rollback()
                except SQLAlchemyError:
                    self.db.invalidate()
                state = getattr(error.orig, 'sqlstate', None)
                disconnected = error.connection_invalidated or (state and state.startswith('08'))
                # Retry a lost connection once, never SQL timeouts or bad queries.
                if attempt or not disconnected:
                    raise
                logger.warning('Geoespacial: reconexión tras lectura interrumpida; SQLSTATE=%s', state or 'sin código')

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
        return [dict(row) for row in self._read(query)]

    def execution(self, execution_id):
        rows = self._read(select(EtlExecution.execution_id, EtlExecution.records_valid,
                                 EtlExecution.processing_date).where(EtlExecution.execution_id == execution_id))
        if not rows:
            return None
        row = SimpleNamespace(**rows[0])
        self._session_versions[execution_id] = (row.records_valid, row.processing_date)
        return row

    def handovers(self, execution_ids):
        # Detect on complete sessions before visual filters; do not depend on
        # a prior visit to Temporal or mutate its stored events.
        events = []
        for execution_id in execution_ids:
            self._records(execution_id)
            if execution_id not in self._session_events:
                self._session_events[execution_id] = tuple(detectar_handovers(
                    [as_temporal_measurement(row) for row in self._session_records[execution_id]]))
            events.extend(self._session_events[execution_id])
        return events

    def available_days(self, execution_ids):
        local_timestamp = func.timezone('America/Guayaquil', HandoverRecord.timestamp_medicion)
        local_minute = func.date_trunc('minute', local_timestamp)
        query = (select(local_minute.label('minuto'), func.count().label('n_mediciones'))
                 .where(HandoverRecord.execution_id.in_(execution_ids))
                 .group_by(local_minute).order_by(local_minute))
        days = {}
        for row in self._read(query):
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
        return [row['hoja_origen'] for row in self._read(
            select(HandoverRecord.hoja_origen)
            .where(HandoverRecord.execution_id == execution_id)
            .distinct().order_by(HandoverRecord.hoja_origen)
        )]

    def measurements(self, execution_ids, hoja, desde=None, hasta=None):
        # Read complete sessions once: the detector needs context beyond the map
        # interval. Filter the map rows without downloading the same session twice.
        start = desde - timedelta(seconds=MAX_CONTINUITY_SECONDS) if desde else None
        return [row for execution_id in execution_ids for row in self._records(execution_id)
                if (hoja is None or row.hoja_origen == hoja)
                and (start is None or row.timestamp_medicion >= start)
                and (hasta is None or row.timestamp_medicion <= hasta)]

    def _records(self, execution_id):
        if execution_id in self._session_records:
            return self._session_records[execution_id]
        version = self._session_versions.get(execution_id)
        if version is not None:
            key = (self.db.get_bind(), execution_id, version)

            def load():
                records = self._read_records(execution_id)
                events = tuple(detectar_handovers([as_temporal_measurement(row) for row in records]))
                return records, events

            records, events = session_cache.get_or_load(key, load)
            self._session_events[execution_id] = events
        else:
            records = self._read_records(execution_id)
        self._session_records[execution_id] = records
        return records

    def _read_records(self, execution_id):
        if self.db is not None and hasattr(self.db, 'get_bind') and self.db.get_bind().dialect.name == 'postgresql':
            return self._stream_records(execution_id)
        started = monotonic()
        rows = []
        cursor = None
        while True:
            query = select(*(getattr(HandoverRecord, field) for field in RECORD_COLUMNS)).where(
                HandoverRecord.execution_id == execution_id)
            if cursor is not None:
                timestamp, report_index, record_id = cursor
                after_index = (and_(HandoverRecord.report_index.is_(None), HandoverRecord.id_registro > record_id)
                               if report_index is None else or_(
                                   HandoverRecord.report_index > report_index,
                                   HandoverRecord.report_index.is_(None),
                                   and_(HandoverRecord.report_index == report_index, HandoverRecord.id_registro > record_id)))
                query = query.where(or_(HandoverRecord.timestamp_medicion > timestamp,
                                        and_(HandoverRecord.timestamp_medicion == timestamp, after_index)))
            query = query.order_by(HandoverRecord.timestamp_medicion,
                                   HandoverRecord.report_index.asc().nullslast(), HandoverRecord.id_registro).limit(READ_BATCH_SIZE)
            batch = self._read(query)
            rows.extend(SessionRecord(**row) for row in batch)
            if len(batch) < READ_BATCH_SIZE:
                break
            last = batch[-1]
            cursor = (last['timestamp_medicion'], last['report_index'], last['id_registro'])
        logger.info('Geoespacial: sesión leída en bloques; registros=%d duración=%.2fs', len(rows), monotonic() - started)
        return tuple(rows)

    def _stream_records(self, execution_id):
        """One sorted query; fetch bounded batches through a PostgreSQL cursor."""
        query = (select(*(getattr(HandoverRecord, field) for field in RECORD_COLUMNS))
                 .where(HandoverRecord.execution_id == execution_id)
                 .order_by(HandoverRecord.timestamp_medicion,
                           HandoverRecord.report_index.asc().nullslast(), HandoverRecord.id_registro)
                 .execution_options(yield_per=READ_BATCH_SIZE))
        started = monotonic()
        for attempt in range(2):
            rows = []
            try:
                result = self.db.execute(query)
                try:
                    for batch in result.mappings().partitions(READ_BATCH_SIZE):
                        rows.extend(SessionRecord(**row) for row in batch)
                finally:
                    result.close()
                self.db.rollback()
                logger.info('Geoespacial: sesión leída por cursor; registros=%d duración=%.2fs',
                            len(rows), monotonic() - started)
                return tuple(rows)
            except DBAPIError as error:
                try:
                    self.db.rollback()
                except SQLAlchemyError:
                    self.db.invalidate()
                state = getattr(error.orig, 'sqlstate', None)
                disconnected = error.connection_invalidated or (state and state.startswith('08'))
                if attempt or not disconnected:
                    raise
                # A new cursor restarts the read; discard partial rows so no
                # duplicates or incomplete session can reach the detector.
                logger.warning('Geoespacial: reiniciando cursor interrumpido; SQLSTATE=%s', state or 'sin código')

    def measurement(self, record_id):
        rows = self._read(select(*(getattr(HandoverRecord, field) for field in RECORD_COLUMNS)).where(
            HandoverRecord.id_registro == record_id))
        return SimpleNamespace(**rows[0]) if rows else None
