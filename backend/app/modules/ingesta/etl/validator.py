"""CSV file limits and per-record validation."""

from app.shared.config import Settings
from app.shared.exceptions import FileValidationError
from app.modules.ingesta.etl.constants import (
    MOTIVO_CID_CENTINELA,
    NET_TYPE_2G,
    NET_TYPE_3G,
    NET_TYPE_LTE,
    SENTINEL_INT32_MAX,
)
from app.shared.file_utils import get_extension


def validate_uploaded_file(filename: str, content: bytes, settings: Settings) -> None:
    if not filename:
        raise FileValidationError("El archivo no tiene nombre.")

    extension = get_extension(filename)
    if extension != ".csv" or extension not in settings.allowed_extensions_set:
        allowed = ".csv"
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
    inequívoco), luego un net_type fuera de los 6 valores confirmados con
    datos reales (LTE, UMTS, HSPA, HSPA+, EDGE, GPRS) — no se inventa un
    mapeo de tecnología para un valor no confirmado, se rechaza el registro
    para que quede visible en la cuarentena en vez de fallar silenciosamente
    o adivinar. Esto también cubre 'UNKNOWN' (confirmado en
    Session_43_20260623_165825.csv, 45 filas, 0.05%): la propia app declara
    que no sabe la tecnología, así que no correspondía inventarle una.
    """
    if data["cid"] == SENTINEL_INT32_MAX:
        return MOTIVO_CID_CENTINELA
    net_type = data["net_type"]
    if net_type != NET_TYPE_LTE and net_type not in NET_TYPE_3G and net_type not in NET_TYPE_2G:
        return f"net_type desconocido: '{net_type}' (no es LTE, UMTS, HSPA, HSPA+, EDGE ni GPRS)"
    return None
