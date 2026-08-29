"""Validaciones de nivel archivo, previas a interpretar su contenido.

Nota de alcance: las validaciones de negocio (hojas esperadas, columnas
obligatorias, tipos de dato) se agregarán en una iteración posterior, una
vez analizado un archivo real de handover. Este módulo solo valida lo que
es válido para *cualquier* Excel: extensión, tamaño y que no esté vacío.
"""

from app.core.config import Settings
from app.core.exceptions import FileValidationError
from app.etl.constants import (
    MOTIVO_CELL_ID_CERO,
    MOTIVO_GPS_SIN_FIX,
    MOTIVO_RSRP_CENTINELA,
)
from app.utils.file_utils import get_extension


def validate_uploaded_file(filename: str, content: bytes, settings: Settings) -> None:
    if not filename:
        raise FileValidationError("El archivo no tiene nombre.")

    extension = get_extension(filename)
    if extension not in settings.allowed_extensions_set:
        allowed = ", ".join(sorted(settings.allowed_extensions_set))
        raise FileValidationError(
            f"Extensión '{extension or '(sin extensión)'}' no soportada. "
            f"Extensiones permitidas: {allowed}."
        )

    if len(content) == 0:
        raise FileValidationError("El archivo está vacío.")

    if len(content) > settings.max_upload_size_bytes:
        raise FileValidationError(
            f"El archivo supera el tamaño máximo permitido "
            f"({settings.max_upload_size_mb} MB)."
        )


def validate_record(data: dict) -> str | None:
    """Valida un registro ya extraído contra las reglas de invalidez dura
    confirmadas con datos reales. Devuelve el motivo de rechazo, o None si
    el registro es válido.

    Orden de precedencia (primera condición que aplica gana): un registro
    con Cell ID/ECI = 0 en los datos reales siempre trae también RSRP = 99,
    así que se reporta el motivo más específico primero.
    """
    if data["Cell ID/ECI"] == 0:
        return MOTIVO_CELL_ID_CERO
    if data["RSRP"] == 99:
        return MOTIVO_RSRP_CENTINELA
    if data["Latitud"] == 0 and data["Longitud"] == 0:
        return MOTIVO_GPS_SIN_FIX
    return None
