from datetime import date
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.shared.db.models import HandoverRecord

class KpisRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_daily_signal_metrics(self, target_date: date) -> dict:
        base_query = self._db.query(HandoverRecord).filter(
            func.date(HandoverRecord.timestamp_medicion) == target_date
        )

        total = base_query.count()

        promedio = self._db.query(func.avg(HandoverRecord.rsrp_dbm)).filter(
            func.date(HandoverRecord.timestamp_medicion) == target_date
        ).scalar() or 0.0

        criticos = base_query.filter(HandoverRecord.rsrp_dbm < -110).count()

        return {
            "total": total,
            "promedio": float(promedio),
            "criticos": criticos
        }

    def get_daily_sequence_data(self, target_date: date) -> list[tuple[int, int]]:
        """
        Extrae la secuencia cronológica de celdas y su nivel de señal.
        """
        records = self._db.query(HandoverRecord.cell_id, HandoverRecord.rsrp_dbm).filter(
            func.date(HandoverRecord.timestamp_medicion) == target_date
        ).order_by(
            HandoverRecord.timestamp_medicion.asc()
        ).all()
        
        return records

    def get_sequence_data_by_range(self, start_date: date, end_date: date) -> list[tuple[int, int]]:
        return self._db.query(HandoverRecord.cell_id, HandoverRecord.rsrp_dbm).filter(
            func.date(HandoverRecord.timestamp_medicion).between(start_date, end_date)
        ).order_by(
            HandoverRecord.timestamp_medicion.asc()
        ).all()

    def get_sequence_with_timestamps(self, start_date: date, end_date: date):
        return self._db.query(
            HandoverRecord.cell_id, 
            HandoverRecord.timestamp_medicion
        ).filter(
            func.date(HandoverRecord.timestamp_medicion).between(start_date, end_date)
        ).order_by(
            HandoverRecord.timestamp_medicion.asc()
        ).all()

    def get_full_sequence_data(self, start_date: date, end_date: date):
        return self._db.query(
            HandoverRecord.cell_id, 
            HandoverRecord.rsrp_dbm,
            HandoverRecord.timestamp_medicion
        ).filter(
            func.date(HandoverRecord.timestamp_medicion).between(start_date, end_date)
        ).order_by(
            HandoverRecord.timestamp_medicion.asc()
        ).all()