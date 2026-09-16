"""Etapa Structure: arma el registro final en el formato exacto que espera
`HandoverRepository.save_valid_records` (columnas de la tabla handover_record).
"""


def structure_record(
    normalized: dict, hoja_origen: str | None, archivo_origen: str, origen_formato: str
) -> dict:
    return {
        **normalized,
        "archivo_origen": archivo_origen,
        "hoja_origen": hoja_origen,
        "origen_formato": origen_formato,
    }
