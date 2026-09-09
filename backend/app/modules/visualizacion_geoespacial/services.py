from collections import Counter

from .schemas import MapData, Measurement


def prepare_map(records, tecnologia=None, cell_id=None, bbox=None):
    """Break routes at excluded points, ambiguous times and gaps over 60 seconds.

    A sheet is a provisional grouping, not a confirmed physical trip. No HO
    detection or speed estimation is performed here.
    """
    if len(records) > 20000:
        raise ValueError("Hay más de 20.000 mediciones. Reduce el intervalo de tiempo.")
    timestamps = Counter(row.timestamp_medicion for row in records)
    points, segments, current = [], [], []
    previous = None
    ambiguous = False
    for row in records:
        lat, lon = float(row.latitud), float(row.longitud)
        selected = (
            -90 <= lat <= 90 and -180 <= lon <= 180
            and (lat, lon) != (0, 0)
            and (tecnologia is None or row.tecnologia == tecnologia)
            and (cell_id is None or row.cell_id == cell_id)
            and (bbox is None or bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3])
        )
        tied = timestamps[row.timestamp_medicion] > 1
        gap = previous is not None and (
            row.hoja_origen != previous.hoja_origen
            or not 0 < (row.timestamp_medicion - previous.timestamp_medicion).total_seconds() <= 60
        )
        if not selected or tied or gap:
            if len(current) > 1:
                segments.append(current)
            current = []
        if selected:
            points.append(Measurement.model_validate(row))
            if not tied:
                current.append(row.id_registro)
        ambiguous = ambiguous or tied
        previous = row if selected and not tied else None
    if len(current) > 1:
        segments.append(current)
    warnings = [
        "Trayectoria aproximada por hoja: confirma que corresponde a un solo recorrido. "
        "Se separan intervalos mayores a 60 segundos y puntos excluidos por filtros.",
        "El mapa de calor representa mediciones, no eventos de handover.",
    ]
    if ambiguous:
        warnings.append("Hay horas repetidas: esos puntos se muestran sin unirlos a la trayectoria.")
    return MapData(mediciones=points, tramos=segments, total=len(points), advertencias=warnings)
