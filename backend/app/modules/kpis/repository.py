"""
Repositorio de acceso a datos del módulo de KPIs.
"""

from datetime import date

from sqlalchemy import extract, func, or_


from sqlalchemy.orm import Session

from app.shared.db.models import EtlExecution, HandoverRecord



import uuid

# Los timestamps se guardan en UTC (ver ingesta/etl/normalizer.py). Sin
# convertir a la zona de origen antes de extraer fecha/hora, Postgres usa
# UTC (zona de la sesión) y desfasa todo 5 horas respecto a la hora real
# en que ocurrió la medición en Ecuador.
ZONA_HORARIA_ORIGEN = "America/Guayaquil"


def _en_hora_local(columna):
    """Convierte una columna timestamptz a la hora local de Ecuador antes
    de extraer componentes de calendario (fecha, hora) en una consulta."""
    return func.timezone(ZONA_HORARIA_ORIGEN, columna)



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
        RSRP procede de rsrp del export de NetMonitor.

        Usado por GET /kpis/daily. No filtra por tecnología: es una vista
        general de calidad de señal, no de handovers.
        """
        consulta_base = self._db.query(HandoverRecord).filter(
            func.date(_en_hora_local(HandoverRecord.timestamp_medicion)) == fecha
        )

        total = consulta_base.count()

        measured = consulta_base.filter(HandoverRecord.rsrp.is_not(None))
        total_rsrp = measured.count()
        promedio = measured.with_entities(func.avg(HandoverRecord.rsrp)).scalar()
        criticos = measured.filter(HandoverRecord.rsrp < -110).count() if total_rsrp else None
        return {"total": total, "total_rsrp": total_rsrp,
                "promedio": float(promedio) if promedio is not None else None, "criticos": criticos}


    def listar_sesiones(self) -> list[EtlExecution]:
        """Lista las sesiones (ejecuciones) completadas, para poblar el
        selector de sesión del frontend -- más recientes primero. No
        incluye ejecuciones fallidas: no tienen datos en handover_record.
        """
        return (
            self._db.query(EtlExecution)
            .filter(EtlExecution.status == "completed")
            .order_by(EtlExecution.sesion_label.desc())
            .all()
        )

    def _resolver_execution_ids_por_sesiones(self, sesiones: list[int]) -> list[uuid.UUID]:
        """Traduce varios sesion_label (identificadores cortos y amigables) a
        sus execution_id reales, para poder filtrar handover_record por
        varias sesiones a la vez.

        Las etiquetas que no existan se traducen a un UUID aleatorio cada
        una (garantiza cero resultados para esa sesión puntual, sin afectar
        a las demás que sí existen) en vez de lanzar un error.
        """
        resultado = []
        for sesion_label in sesiones:
            ejecucion = (
                self._db.query(EtlExecution)
                .filter(EtlExecution.sesion_label == sesion_label)
                .one_or_none()
            )
            resultado.append(ejecucion.execution_id if ejecucion else uuid.uuid4())
        return resultado

    def _condicion_franjas(self, franjas: list[str]):
        """Arma la condición SQL (OR de rangos horarios) para una lista de
        franjas horarias. Ver FRANJA_RANGOS_HORA para mañana/tarde; noche se
        maneja aparte por envolver la medianoche."""
        hora = extract("hour", _en_hora_local(HandoverRecord.timestamp_medicion))
        condiciones = []
        for franja in franjas:
            if franja == "noche":
                condiciones.append((hora >= 19) | (hora <= 5))
            else:
                hora_min, hora_max = FRANJA_RANGOS_HORA[franja]
                condiciones.append(hora.between(hora_min, hora_max))
        return or_(*condiciones)



    def contar_mediciones(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        tecnologia: list[int] | None = None,
        franja: list[str] | None = None,
        sesion_label: list[int] | None = None,
    ) -> int:
        """Total de mediciones (filas de handover_record) en el rango dado.

        Es el denominador de la tasa de handover (total_ho / total de
        mediciones). Los 3 filtros opcionales son listas: una selección
        vacía o None se trata como "todas" (sin filtro), no como "ninguna".
        """
        consulta = self._db.query(func.count(HandoverRecord.id_registro)).filter(
            func.date(_en_hora_local(HandoverRecord.timestamp_medicion)).between(fecha_inicio, fecha_fin)
        )
        if tecnologia:
            consulta = consulta.filter(HandoverRecord.tecnologia.in_(tecnologia))
        if franja:
            consulta = consulta.filter(self._condicion_franjas(franja))
        if sesion_label:
            consulta = consulta.filter(
                HandoverRecord.execution_id.in_(self._resolver_execution_ids_por_sesiones(sesion_label))
            )
        return consulta.scalar() or 0




    def obtener_secuencia_completa(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        tecnologia: list[int] | None = None,
        sesion_label: list[int] | None = None,
    ) -> list[tuple]:
        """Secuencia de mediciones del rango, con todos los indicadores de
        señal necesarios para detectar handovers y clasificarlos:
        (cell_id, timestamp_medicion, rsrp_dbm, rssi, rsrq, rssnr,
        execution_id, tecnologia, report_index).

        `tecnologia`/`sesion_label` son listas opcionales (ver
        `contar_mediciones`). `franja` no se filtra aquí -- se aplica
        después de detectar los eventos, en services.py.

        `execution_id`, `tecnologia` y `report_index` viajan en cada fila
        para que `services.py` pueda: (a) agrupar la secuencia por sesión
        antes de detectar handovers -- nunca se detecta un salto entre
        mediciones de sesiones distintas --, y (b) desempatar mediciones
        con el mismo `timestamp_medicion` por su orden de reporte original.

        Reemplaza a los antiguos `get_sequence_data_by_range`,
        `get_sequence_with_timestamps` y `get_full_sequence_data`: los tres
        hacían la misma consulta con un subconjunto distinto de columnas.
        Un solo método evita mantener 3 queries casi idénticas sincronizadas
        a mano; el costo de traer columnas que algún servicio no usa es
        despreciable frente a eso.

        Ordenado por (execution_id, timestamp_medicion, report_index): ese
        orden agrupa automáticamente las mediciones de cada sesión de forma
        contigua y cronológica, con desempate -- services.py solo necesita
        detectar cuándo cambia el execution_id para saber que empezó una
        sesión nueva, sin tener que agrupar él mismo.
        """
        consulta = self._db.query(
            HandoverRecord.cell_id,
            HandoverRecord.timestamp_medicion,
            HandoverRecord.rsrp.label("rsrp_dbm"),
            HandoverRecord.rssi,
            HandoverRecord.rsrq,
            HandoverRecord.rssnr,
            HandoverRecord.execution_id,
            HandoverRecord.tecnologia,
            HandoverRecord.report_index,
        ).filter(func.date(_en_hora_local(HandoverRecord.timestamp_medicion)).between(fecha_inicio, fecha_fin))
        if tecnologia:
            consulta = consulta.filter(HandoverRecord.tecnologia.in_(tecnologia))
        if sesion_label:
            consulta = consulta.filter(
                HandoverRecord.execution_id.in_(self._resolver_execution_ids_por_sesiones(sesion_label))
            )
        return consulta.order_by(
            HandoverRecord.execution_id.asc(),
            HandoverRecord.timestamp_medicion.asc(),
            HandoverRecord.report_index.asc(),
        ).all()
