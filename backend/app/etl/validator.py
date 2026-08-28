"""Validaciones de nivel archivo, previas a interpretar su contenido.

Nota de alcance: las validaciones de negocio (hojas esperadas, columnas
obligatorias, tipos de dato) se agregarán en una iteración posterior, una
vez analizado un archivo real de handover. Este módulo solo valida lo que
es válido para *cualquier* Excel: extensión, tamaño y que no esté vacío.
"""

from app.core.config import Settings
from app.core.exceptions import FileValidationError
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
