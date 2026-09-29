from collections import Counter

from .schemas import HandoverEvent, MapData, Measurement
from .radio_bases import estimate_radio_bases


def prepare_map(records, tecnologia=None, cell_id=None, bbox=None, desde=None):
    """Break routes at excluded points, ambiguous times and gaps over 60 seconds.

    Detect simultaneous changes in cell_id AND node_id before applying visual
    filters. Locate each event at the first observation of its destination.
    """
    if len(records) > 20000:
        raise ValueError("Hay más de 20.000 mediciones. Reduce el intervalo de tiempo.")
    def session(row):
        return str(getattr(row, "execution_id", "")), row.hoja_origen or ""

    records = sorted(records, key=lambda row: (*session(row), row.timestamp_medicion, str(row.id_registro)))
    timestamps = Counter((*session(row), row.timestamp_medicion) for row in records)
    points, segments, current = [], [], []
    previous = None
    previous_observation = None
    events = []
    ambiguous = False
    for row in records:
        lat, lon = float(row.latitud), float(row.longitud)
        selected = (
            -90 <= lat <= 90 and -180 <= lon <= 180
            and (lat, lon) != (0, 0)
            and (tecnologia is None or row.tecnologia == tecnologia)
            and (cell_id is None or row.cell_id == cell_id)
            and (desde is None or row.timestamp_medicion >= desde)
            and (bbox is None or bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3])
        )
        measurement = Measurement.model_validate(row) if selected else None
        tied = timestamps[(*session(row), row.timestamp_medicion)] > 1
        node = getattr(row, "node_id", None)
        valid_identity = node is not None and 0 < node < 2147483647 and 0 < row.cell_id < 2147483647
        before = previous_observation
        if selected and not tied and valid_identity and before is not None and (
            session(before) == session(row)
            and 0 < (row.timestamp_medicion - before.timestamp_medicion).total_seconds() <= 60
            and before.cell_id != row.cell_id
            and before.node_id != node
        ):
            events.append(HandoverEvent(
                **measurement.model_dump(),
                registro_anterior_id=before.id_registro,
                celda_origen=before.cell_id,
                nodo_origen=before.node_id,
            ))
        previous_observation = row if valid_identity and not tied else None
        gap = previous is not None and (
            session(row) != session(previous)
            or not 0 < (row.timestamp_medicion - previous.timestamp_medicion).total_seconds() <= 60
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
        "Handovers según la regla acordada: cambian cell_id y node_id a la vez. "
        "Se ubican en la primera medición de destino; no se comparan hojas distintas, "
        "horas repetidas, identificadores ausentes ni intervalos mayores a 60 segundos.",
    ]
    if ambiguous:
        warnings.append("Hay horas repetidas: esos puntos se muestran sin unirlos a la trayectoria.")
    if any(getattr(row, "node_id", None) is None for row in records):
        warnings.append("Hay mediciones sin node_id: no permiten evaluar la regla de handover.")
    radios_base, resumen_radios_base = estimate_radio_bases(points)
    return MapData(mediciones=points, tramos=segments, total=len(points),
                   handovers=events, total_handovers=len(events), advertencias=warnings,
                   radios_base=radios_base, resumen_radios_base=resumen_radios_base)
