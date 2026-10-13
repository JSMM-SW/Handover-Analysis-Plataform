"""Regla que asigna `tecnologia` a un registro csv.

Aislada en este módulo a propósito: `tecnologia` se deriva de `tech`, no de
`net_type` (ver TECH_A_TECNOLOGIA en constants.py), y esa decisión todavía
debe coordinarse con los demás módulos. Las filas históricas siguen con la
regla anterior (net_type) y NO se recalculan. Revertir a `net_type` es
cambiar solo `motivo_rechazo_tecnologia_csv` y `map_tecnologia_csv` aquí;
el Validator, el Normalizer y services.py solo llaman a estas funciones.
"""

from app.modules.ingesta.etl.constants import (
    MOTIVO_TECNOLOGIA_AUSENTE,
    NET_TYPE_2G,
    NET_TYPE_3G,
    NET_TYPE_LTE,
    TECH_A_TECNOLOGIA,
    TECNOLOGIA_2G,
    TECNOLOGIA_3G,
    TECNOLOGIA_LTE,
)


def motivo_rechazo_tecnologia_csv(data: dict) -> str | None:
    """Motivo de rechazo si la fila no permite asignar `tecnologia` (NOT
    NULL), o None. `tech` vacío o fuera de LTE/WCDMA/GSM rechaza la fila: no
    se inventa un mapeo para un valor no confirmado. `net_type` no se valida
    (es informativo), así que 'UNKNOWN' en net_type no rechaza la fila.
    """
    if "tech" in data and data["tech"] is None:
        return MOTIVO_TECNOLOGIA_AUSENTE
    tech = data["tech"]
    if tech not in TECH_A_TECNOLOGIA:
        return f"tech desconocido: '{tech}' (no es LTE, WCDMA ni GSM)"
    return None


def map_tecnologia_csv(tech: str) -> int:
    """Mapea `tech` a los códigos de `tecnologia`. Asume que `tech` ya pasó
    `motivo_rechazo_tecnologia_csv`."""
    return TECH_A_TECNOLOGIA[tech]


def tecnologia_csv(data: dict) -> int:
    """`tecnologia` de un registro csv ya validado."""
    return map_tecnologia_csv(data["tech"])


def _tecnologia_segun_net_type(net_type) -> int | None:
    """Solo para auditoría: qué `tecnologia` habría sugerido `net_type` (la
    regla anterior). None si net_type no es uno de los 6 valores conocidos."""
    if net_type == NET_TYPE_LTE:
        return TECNOLOGIA_LTE
    if net_type in NET_TYPE_3G:
        return TECNOLOGIA_3G
    if net_type in NET_TYPE_2G:
        return TECNOLOGIA_2G
    return None


def net_type_audit_warnings(valid_records: list[dict]) -> list[str]:
    """Warnings agregados (no por fila) de discrepancia net_type vs tech. No
    cambian nada: `tecnologia` ya se tomó de `tech`."""
    distinto = desconocido = 0
    for record in valid_records:
        sugerida = _tecnologia_segun_net_type(record["net_type"])
        if sugerida is None:
            desconocido += 1
        elif sugerida != record["tecnologia"]:
            distinto += 1
    warnings = []
    if distinto:
        warnings.append(
            f"{distinto} registro(s) csv donde net_type sugiere una tecnología distinta a tech "
            "(tecnologia se tomó de tech; net_type se guarda solo como dato informativo)"
        )
    if desconocido:
        warnings.append(
            f"{desconocido} registro(s) csv con net_type no reconocido (ej. 'UNKNOWN') o vacío, "
            "conservados: tecnologia se tomó de tech"
        )
    return warnings
