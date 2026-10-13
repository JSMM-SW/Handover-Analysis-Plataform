"""Etapa Normalize: unifica formatos y convierte a los tipos/unidades del
formato estándar de salida (Objetivo 3 del plan de tesis).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.modules.ingesta.etl.constants import TIMEZONE_ORIGEN
from app.modules.ingesta.etl.tecnologia import map_tecnologia_csv, tecnologia_csv  # noqa: F401

_ORIGEN_TZ = ZoneInfo(TIMEZONE_ORIGEN)


def _opt(value, cast):
    """`cast(value)`, o None si el valor está ausente (columna opcional que
    no existe en el archivo, celda vacía o centinela ya nuleado)."""
    return None if value is None else cast(value)


def _position(latitud, longitud) -> tuple[float | None, float | None]:
    """Coordenadas como par: si falta una de las dos, ambas quedan NULL (una
    latitud sin longitud no es una posición utilizable)."""
    if latitud is None or longitud is None:
        return None, None
    return float(latitud), float(longitud)


def normalize_sys_time(sys_time) -> datetime:
    """Parsea `sys_time` (formato AAAAMMDDHHMMSS, 14 dígitos) a datetime UTC.

    La hora local America/Guayaquil (UTC-5) se convierte a UTC.
    """
    sys_time_str = str(int(sys_time)).zfill(14)

    local_dt = datetime(
        year=int(sys_time_str[0:4]),
        month=int(sys_time_str[4:6]),
        day=int(sys_time_str[6:8]),
        hour=int(sys_time_str[8:10]),
        minute=int(sys_time_str[10:12]),
        second=int(sys_time_str[12:14]),
        tzinfo=_ORIGEN_TZ,
    )
    return local_dt.astimezone(timezone.utc)


def normalize_record_csv(data: dict) -> dict:
    """Convierte un registro crudo de csv (ya validado y con centinelas
    nuleados por `cleaner.apply_sentinels_csv`) a los tipos del dataset
    final.

    Las señales se conservan tal como vienen del CSV, sin inferir otra
    medida según la tecnología: `rssi` -> rssi y `rssi_strongest` -> rsrp
    (RSRP de NetMonitor, ver docs/migracion_csv_senales.md).

    `tecnologia` se asigna en etl/tecnologia.py (desde `tech`; `net_type` se
    guarda solo como dato informativo). Todo campo salvo sys_time/cid/tech
    (garantizados por el Validator) puede venir None: columna opcional
    ausente en el archivo, celda vacía o centinela nuleado. Se guarda NULL.
    """
    # NULL cuando cleaner.apply_sentinels_csv anuló gps sin fix (ya no se
    # rechaza el registro completo por esto, ver validator.py).
    latitud, longitud = _position(data["lat"], data["long"])

    return {
        "timestamp_medicion": normalize_sys_time(data["sys_time"]),
        "cell_id": int(data["cid"]),
        "tac": _opt(data["lac_tac"], int),
        "earfcn": _opt(data["arfcn"], int),
        "tecnologia": tecnologia_csv(data),
        "latitud": latitud,
        "longitud": longitud,
        "rssi": _opt(data["rssi"], int),
        "rsrp": _opt(data.get("rssi_strongest"), int),
        "node_id": _opt(data["node_id"], int),
        "psc_pci": _opt(data["psc_pci"], int),
        "rsrq": _opt(data["rsrq"], int),
        "rssnr": _opt(data["rssnr"], int),
        "accuracy": _opt(data["accuracy"], int),
        # Identificadores crudos, además de cell_id/tac (ver comentario de
        # cell_id en schema.sql sobre la ambigüedad de identidad en LTE).
        "cid": int(data["cid"]),
        "lac_tac_raw": _opt(data["lac_tac"], int),
        "report_index": _opt(data["report"], int),
        "net_type": _opt(data["net_type"], str),  # informativo, no decide tecnologia
        "tech": _opt(data["tech"], str),
        "data_state": _opt(data["data_state"], str),
        "call_state": _opt(data["call_state"], str),
    }
