from collections import Counter
from zoneinfo import ZoneInfo

from .schemas import HandoverEvent, MapData, Measurement
from .radio_bases import estimate_radio_bases
from .constants import MAX_CONTINUITY_SECONDS


def prepare_map(records, tecnologia=None, cell_id=None, bbox=None, desde=None, hora_inicio=None, hora_fin=None,
                detected_events=()):
    """Break routes at excluded points, ambiguous times and gaps over 60 seconds.

    Use Temporal events detected on complete sessions. GPS controls plotting,
    never whether an otherwise selected event contributes to the total.
    """
    def session(row):
        return str(getattr(row, "execution_id", "")), row.hoja_origen or ""

    records = sorted(records, key=lambda row: (*session(row), row.timestamp_medicion, str(row.id_registro)))
    timestamps = Counter((*session(row), row.timestamp_medicion) for row in records)
    points, segments, current = [], [], []
    previous = None
    events = []
    total_events = 0
    events_by_destination = {event.medicion_posterior_id: event for event in detected_events}
    ambiguous = False
    for row in records:
        local_time = row.timestamp_medicion.astimezone(ZoneInfo('America/Guayaquil')).time() if hora_inicio or hora_fin else None
        # Ingestion preserves radio observations without a GPS fix. Keep them
        # as handover context, but never plot them or bridge a route across them.
        lat = float(row.latitud) if row.latitud is not None else None
        lon = float(row.longitud) if row.longitud is not None else None
        valid_gps = (lat is not None and lon is not None
                     and -90 <= lat <= 90 and -180 <= lon <= 180 and (lat, lon) != (0, 0))
        included = (
            (tecnologia is None or row.tecnologia == tecnologia)
            and (cell_id is None or row.cell_id == cell_id)
            and (desde is None or row.timestamp_medicion >= desde)
            and (hora_inicio is None or local_time >= hora_inicio)
            and (hora_fin is None or local_time <= hora_fin)
            and (bbox is None or valid_gps and bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3])
        )
        selected = included and valid_gps
        measurement = Measurement.model_validate(row) if selected else None
        tied = timestamps[(*session(row), row.timestamp_medicion)] > 1
        event = events_by_destination.get(str(row.id_registro))
        if included and event is not None:
            total_events += 1
            if selected:
                events.append(HandoverEvent(
                    **measurement.model_dump(),
                    registro_anterior_id=event.medicion_previa_id,
                    celda_origen=event.celda_origen_cid,
                    nodo_origen=event.celda_origen_node_id,
                ))
        gap = previous is not None and (
            session(row) != session(previous)
            or not 0 < (row.timestamp_medicion - previous.timestamp_medicion).total_seconds() <= MAX_CONTINUITY_SECONDS
        )
        if not selected or tied or gap:
            if len(current) > 1:
                segments.append(current)
            current = []
        if selected:
            points.append(measurement)
            if not tied:
                current.append(row.id_registro)
        ambiguous = ambiguous or tied
        previous = row if selected and not tied else None
    if len(current) > 1:
        segments.append(current)
    warnings = [
        "Trayectoria aproximada por hoja: confirma que corresponde a un solo recorrido. "
        "Se separan intervalos mayores a 60 segundos y puntos excluidos por filtros.",
        "Handovers inferidos con el detector de Temporal: identidad de celda, "
        "confirmación de dos muestras y límite de 30 segundos entre celdas. "
        "Se calculan por sesión completa; solo los eventos con GPS válido se dibujan.",
    ]
    if ambiguous:
        warnings.append("Hay horas repetidas: esos puntos se muestran sin unirlos a la trayectoria.")
    radios_base, resumen_radios_base = estimate_radio_bases(points)
    return MapData(mediciones=points, tramos=segments, total=len(points),
                   handovers=events, total_handovers=total_events, advertencias=warnings,
                   handovers_con_ubicacion=len(events), handovers_sin_ubicacion=total_events - len(events),
                   radios_base=radios_base, resumen_radios_base=resumen_radios_base)
