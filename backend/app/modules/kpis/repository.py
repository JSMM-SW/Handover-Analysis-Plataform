"""
Repositorio de acceso a datos del módulo de KPIs.
"""

from datetime import date

from sqlalchemy import extract, func

from sqlalchemy.orm import Session

from app.shared.db.models import HandoverRecord

# Rangos de hora [min, max] cerrados para mañana/tarde. "noche" no entra
# aquí porque envuelve la medianoche (19-23 y 0-5), se maneja aparte.
FRANJA_RANGOS_HORA = {
    "manana": (6, 11),
    "tarde": (12, 18),
}
 
class KpisRepository:
    """Consultas de solo lectura sobre `handover_record` para KPIs."""

    def __init__(self, db: Session):
        self._db = db

    def obtener_metricas_diarias_senal(self, fecha: date) -> dict:
        """Calidad de señal general de un día puntual: total de mediciones,
        promedio de RSRP y número de mediciones críticas (RSRP < -110 dBm).

        Usado por GET /kpis/daily. No filtra por tecnología: es una vista
        general de calidad de señal, no de handovers.
        """
        consulta_base = self._db.query(HandoverRecord).filter(
            func.date(HandoverRecord.timestamp_medicion) == fecha
        )

        total = consulta_base.count()

        promedio = (
            self._db.query(func.avg(HandoverRecord.rsrp_dbm))
            .filter(func.date(HandoverRecord.timestamp_medicion) == fecha)
            .scalar()
            or 0.0
        )

        criticos = consulta_base.filter(HandoverRecord.rsrp_dbm < -110).count()

        return {"total": total, "promedio": float(promedio), "criticos": criticos}


    def contar_mediciones(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        tecnologia: int | None = None,
        franja: str | None = None,
    ) -> int:
        """Total de mediciones (filas de handover_record) en el rango dado.

        Es el denominador de la tasa de handover (total_ho / total de
        mediciones). `tecnologia` es opcional: 0=sin señal, 1=LTE/4G,
        2=3G/UMTS. `franja` es opcional: 'manana', 'tarde' o 'noche' (ver
        FRANJA_RANGOS_HORA) -- filtra por la hora del día de la medición,
        no por fecha.
        """
        consulta = self._db.query(func.count(HandoverRecord.id_registro)).filter(
            func.date(HandoverRecord.timestamp_medicion).between(fecha_inicio, fecha_fin)
        )
        if tecnologia is not None:
            consulta = consulta.filter(HandoverRecord.tecnologia == tecnologia)
        if franja is not None:
            hora = extract("hour", HandoverRecord.timestamp_medicion)
            if franja == "noche":
                consulta = consulta.filter((hora >= 19) | (hora <= 5))
            else:
                hora_min, hora_max = FRANJA_RANGOS_HORA[franja]
                consulta = consulta.filter(hora.between(hora_min, hora_max))
        return consulta.scalar() or 0



    def obtener_secuencia_completa(
        self, fecha_inicio: date, fecha_fin: date, tecnologia: int | None = None
    ) -> list[tuple]:
        """Secuencia cronológica de mediciones del rango, con todos los
        indicadores de señal necesarios para detectar handovers y
        clasificarlos como exitosos/fallidos: cell_id, timestamp, rsrp_dbm,
        rssi, rsrq, rssnr.

        Reemplaza a los antiguos `get_sequence_data_by_range`,
        `get_sequence_with_timestamps` y `get_full_sequence_data`: los tres
        hacían la misma consulta con un subconjunto distinto de columnas.
        Un solo método evita mantener 3 queries casi idénticas sincronizadas
        a mano; el costo de traer columnas que algún servicio no usa es
        despreciable frente a eso.

        Ordenado por timestamp ascendente: ese orden es lo que le permite a
        los servicios detectar una transición de celda comparando cada
        registro contra el anterior.
        """
        consulta = self._db.query(
            HandoverRecord.cell_id,
            HandoverRecord.timestamp_medicion,
            HandoverRecord.rsrp_dbm,
            HandoverRecord.rssi,
            HandoverRecord.rsrq,
            HandoverRecord.rssnr,
        ).filter(func.date(HandoverRecord.timestamp_medicion).between(fecha_inicio, fecha_fin))
        if tecnologia is not None:
            consulta = consulta.filter(HandoverRecord.tecnologia == tecnologia)
        return consulta.order_by(HandoverRecord.timestamp_medicion.asc()).all()
