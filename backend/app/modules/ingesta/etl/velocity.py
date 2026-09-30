"""Cálculo de `velocidad_kmh`: distancia (Haversine) entre un registro y el
inmediato anterior de la misma sesión, dividida entre la diferencia de
tiempo.

"Misma sesión" = misma `hoja_origen`. Para xlsx esto significa por hoja, NO
toda la ejecución combinada: las hojas de un Excel real representan pases
de manejo distintos (confirmado con datos reales: combinarlas produce
saltos de tiempo hacia atrás en el orden de extracción). Para csv,
`hoja_origen` siempre es None (no tiene el concepto de hojas), así que toda
la ejecución cae en un solo grupo — correcto, porque cada archivo csv ya es
una sesión de manejo continua.

Cuando dos registros comparten exactamente el mismo `timestamp_medicion`
(ocurre en datos reales de xlsx, resolución de 1 segundo), se tratan como
el mismo instante: diferencia de tiempo 0 -> NULL. No se intenta desempatar
cuál fue "primero".
"""

import math

from app.modules.ingesta.etl.constants import VELOCIDAD_MAX_ESPERADA_KMH

EARTH_RADIUS_KM = 6371.0088


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def compute_velocities(valid_records: list[dict], gps_reject_anchors: list[tuple]) -> list[str]:
    """Calcula `velocidad_kmh` para cada registro de `valid_records`, en el
    lugar (agrega/sobreescribe la clave en cada dict). Devuelve la lista de
    warnings por velocidades inusuales (> VELOCIDAD_MAX_ESPERADA_KMH); esas
    velocidades se guardan igual, no se rechazan ni se fuerzan a NULL.

    `gps_reject_anchors` es una lista de (timestamp_medicion, hoja_origen)
    de los registros rechazados específicamente por "gps sin fix" (motivo
    exacto, no cualquier rechazo): no aportan coordenadas utilizables, pero
    su posición en el tiempo sí importa — invalidan la velocidad del
    registro válido inmediatamente siguiente en la misma sesión. Otros
    motivos de rechazo (cid centinela, duplicado, fuera de rango, etc.) no
    rompen la cadena: no se usan como ancla ni bloquean el cálculo, dado que
    la regla de negocio solo menciona GPS sin fix como caso de invalidación.
    """
    entries = [
        {
            "timestamp": record["timestamp_medicion"],
            "hoja_origen": record["hoja_origen"],
            "is_valid": True,
            "record": record,
        }
        for record in valid_records
    ]
    entries.extend(
        {"timestamp": timestamp, "hoja_origen": hoja_origen, "is_valid": False, "record": None}
        for timestamp, hoja_origen in gps_reject_anchors
    )

    groups: dict[object, list[dict]] = {}
    for entry in entries:
        groups.setdefault(entry["hoja_origen"], []).append(entry)

    warnings: list[str] = []

    for group_entries in groups.values():
        group_entries.sort(key=lambda e: e["timestamp"])
        previous = None
        for entry in group_entries:
            if entry["is_valid"]:
                record = entry["record"]
                if previous is None or not previous["is_valid"]:
                    record["velocidad_kmh"] = None
                else:
                    dt_seconds = (entry["timestamp"] - previous["timestamp"]).total_seconds()
                    if dt_seconds == 0:
                        record["velocidad_kmh"] = None
                    else:
                        prev_record = previous["record"]
                        distance_km = _haversine_km(
                            float(prev_record["latitud"]),
                            float(prev_record["longitud"]),
                            float(record["latitud"]),
                            float(record["longitud"]),
                        )
                        velocidad = round(distance_km / (dt_seconds / 3600), 2)
                        record["velocidad_kmh"] = velocidad
                        if velocidad > VELOCIDAD_MAX_ESPERADA_KMH:
                            warnings.append(
                                f"velocidad inusual ({velocidad} km/h) entre registros de "
                                f"{previous['timestamp'].isoformat()} y {entry['timestamp'].isoformat()}"
                            )
            previous = entry

    return warnings
