"""Etapa Clean: reglas de calidad de datos que aplican sobre registros que ya
pasaron las validaciones estructurales duras del Validator (etl/validator.py).
"""

from app.etl.constants import (
    LATITUD_MAX,
    LATITUD_MIN,
    LONGITUD_MAX,
    LONGITUD_MIN,
    MOTIVO_COORDENADAS_FUERA_DE_RANGO,
    MOTIVO_RSRP_FUERA_DE_RANGO,
    REQUIRED_COLUMNS,
    RSRP_MAX_VALID,
    RSRP_MIN_VALID,
)


def validate_ranges(data: dict) -> str | None:
    """Verifica que RSRP y coordenadas estén dentro de rangos físicamente
    plausibles. Devuelve el motivo de rechazo, o None si el registro pasa.
    """
    rsrp = data["RSRP"]
    if not (RSRP_MIN_VALID <= rsrp <= RSRP_MAX_VALID):
        return MOTIVO_RSRP_FUERA_DE_RANGO

    latitud, longitud = data["Latitud"], data["Longitud"]
    if not (LATITUD_MIN <= latitud <= LATITUD_MAX) or not (
        LONGITUD_MIN <= longitud <= LONGITUD_MAX
    ):
        return MOTIVO_COORDENADAS_FUERA_DE_RANGO

    return None


def deduplicate(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separa duplicados exactos (mismo valor en las 9 columnas de negocio).

    Conserva la primera aparición en el orden recibido; las siguientes
    apariciones idénticas se devuelven como rechazadas. El orden de entrada
    determina qué copia sobrevive: dado que los valores son idénticos, la
    fila conservada es intercambiable con la rechazada salvo por su
    `hoja_origen`/`fila_excel`.
    """
    seen: set[tuple] = set()
    unique: list[dict] = []
    duplicates: list[dict] = []

    for record in records:
        key = tuple(record["data"][col] for col in REQUIRED_COLUMNS)
        if key in seen:
            duplicates.append(record)
        else:
            seen.add(key)
            unique.append(record)

    return unique, duplicates
