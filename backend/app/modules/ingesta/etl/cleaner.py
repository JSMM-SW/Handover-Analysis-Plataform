"""Etapa Clean: reglas de calidad de datos que aplican sobre registros que ya
pasaron las validaciones estructurales duras del Validator (etl/validator.py).
"""

from app.modules.ingesta.etl.constants import (
    ACCURACY_SIN_DATO,
    CAMPOS_CENTINELA_CSV_NULEABLES,
    LATITUD_MAX,
    LATITUD_MIN,
    LONGITUD_MAX,
    LONGITUD_MIN,
    MOTIVO_COORDENADAS_FUERA_DE_RANGO,
    MOTIVO_RSRP_FUERA_DE_RANGO,
    RSRP_MAX_VALID,
    RSRP_MIN_VALID,
    SENTINEL_INT32_MAX,
)


def validate_ranges(data: dict) -> str | None:
    """Verifica que RSRP y coordenadas estén dentro de rangos físicamente
    plausibles (origen xlsx). Devuelve el motivo de rechazo, o None si el
    registro pasa.
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


def apply_sentinels_csv(data: dict) -> tuple[dict, list[str]]:
    """Reemplaza los centinelas por None en los campos donde eso NO implica
    rechazar el registro (todo excepto `cid`, que ya se rechaza en el
    Validator). Devuelve (data_limpia, nombres_de_campos_nuleados).

    `accuracy` usa un centinela propio (-1) distinto del resto (2147483647),
    pero se trata igual: se guarda NULL y se cuenta para el warning agregado.

    No modifica `data` en el lugar: devuelve una copia, porque `data` original
    se usa como `datos_crudos` si el registro terminara rechazado por otra
    regla posterior (duplicado).
    """
    cleaned = dict(data)
    nulled_fields: list[str] = []
    for field in CAMPOS_CENTINELA_CSV_NULEABLES:
        if cleaned[field] == SENTINEL_INT32_MAX:
            cleaned[field] = None
            nulled_fields.append(field)
    if cleaned["accuracy"] == ACCURACY_SIN_DATO:
        cleaned["accuracy"] = None
        nulled_fields.append("accuracy")
    return cleaned, nulled_fields


def deduplicate(records: list[dict], key_columns: list[str]) -> tuple[list[dict], list[dict]]:
    """Separa duplicados exactos (mismo valor en las columnas de `key_columns`).

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
        key = tuple(record["data"][col] for col in key_columns)
        if key in seen:
            duplicates.append(record)
        else:
            seen.add(key)
            unique.append(record)

    return unique, duplicates
