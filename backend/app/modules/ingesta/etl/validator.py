"""CSV file limits and per-record validation."""

from app.shared.config import Settings
from app.shared.exceptions import FileValidationError
from app.modules.ingesta.etl.constants import (
    MOTIVO_CELDA_AUSENTE,
    MOTIVO_CID_CENTINELA,
    MOTIVO_TIMESTAMP_AUSENTE,
    SENTINEL_INT32_MAX,
)
from app.modules.ingesta.etl.tecnologia import motivo_rechazo_tecnologia_csv
from app.shared.file_utils import get_extension


def _megabytes(size_bytes: int) -> str:
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def validate_uploaded_file(filename: str, content: bytes, settings: Settings) -> None:
    validate_upload_metadata(filename, len(content), settings)


def validate_upload_metadata(filename: str, size_bytes: int, settings: Settings) -> None:
    """Validaciones de archivo que no requieren leer su contenido: nombre,
    extensión y tamaño (la subida en streaming conoce el tamaño sin cargar el
    archivo en memoria)."""
    if not filename:
        raise FileValidationError("El archivo no tiene nombre.")

    extension = get_extension(filename)
    if extension != ".csv" or extension not in settings.allowed_extensions_set:
        allowed = ".csv"
        raise FileValidationError(
            f"Extensión '{extension or '(sin extensión)'}' no soportada. "
            f"Extensiones permitidas: {allowed}."
        )

    if size_bytes == 0:
        raise FileValidationError("El archivo está vacío.")

    if size_bytes > settings.max_upload_size_bytes:
        raise FileValidationError(
            f"El archivo pesa {_megabytes(size_bytes)} y supera el tamaño máximo permitido "
            f"({settings.max_upload_size_mb} MB)."
        )


def _vacio(data: dict, *campos: str) -> bool:
    """True si alguno de `campos` vino vacío (None: celda en blanco o columna
    ausente en el archivo — el extractor siempre entrega la clave)."""
    return any(campo in data and data[campo] is None for campo in campos)


def validate_record_csv(data: dict) -> str | None:
    """Devuelve el motivo de
    rechazo, o None si el registro es válido.

    Se valida solo por `cid` e identidad de tecnología — NO por GPS: gps sin
    fix (gps=0, o lat=long=-1) ya no rechaza el registro (confirmado con
    Session_43_20260623_165825.csv: rechazar por esto tira el 92% del
    archivo y el módulo de visualización temporal no usa coordenadas). Esos
    registros se conservan con latitud/longitud NULL — ver
    `cleaner.apply_sentinels_csv`.

    Orden de precedencia: `cid` centinela primero (rechazo específico e
    inequívoco), luego un `tech` fuera de los 3 valores confirmados (LTE,
    WCDMA, GSM) — no se inventa un mapeo de tecnología para un valor no
    confirmado, se rechaza el registro para que quede visible en la
    cuarentena. `net_type` ya NO se valida: es informativo (ver
    etl/tecnologia.py), así que 'UNKNOWN' u otro valor raro en net_type no
    rechaza la fila.

    Antes de todo eso: `sys_time`, `cid` o `tech` (fuente de `tecnologia`,
    NOT NULL) vacíos rechazan la fila con un motivo explícito.
    """
    if _vacio(data, "sys_time"):
        return MOTIVO_TIMESTAMP_AUSENTE
    if _vacio(data, "cid"):
        return MOTIVO_CELDA_AUSENTE
    if data["cid"] == SENTINEL_INT32_MAX:
        return MOTIVO_CID_CENTINELA
    # Regla de tecnología (tech, no net_type) aislada en etl/tecnologia.py.
    return motivo_rechazo_tecnologia_csv(data)
