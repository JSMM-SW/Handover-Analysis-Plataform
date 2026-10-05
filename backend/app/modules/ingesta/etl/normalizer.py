"""Etapa Normalize: unifica formatos y convierte a los tipos/unidades del
formato estándar de salida (Objetivo 3 del plan de tesis).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.modules.ingesta.etl.constants import (
    NET_TYPE_3G,
    NET_TYPE_LTE,
    TECNOLOGIA_2G,
    TECNOLOGIA_3G,
    TECNOLOGIA_LTE,
    TIMEZONE_ORIGEN,
)

_ORIGEN_TZ = ZoneInfo(TIMEZONE_ORIGEN)


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


def map_tecnologia_csv(net_type: str) -> int:
    """Mapea `net_type` (fuente de verdad confirmada, más confiable que
    `tech` — ver constants.py) a los códigos de `tecnologia`.

    Asume que `net_type` ya fue validado como uno de los 6 valores
    confirmados (LTE, UMTS, HSPA, HSPA+, EDGE, GPRS) por `validate_record_csv`;
    cualquier otro valor ('UNKNOWN' incluido) ya habría sido rechazado antes
    de llegar aquí.
    """
    if net_type == NET_TYPE_LTE:
        return TECNOLOGIA_LTE
    if net_type in NET_TYPE_3G:
        return TECNOLOGIA_3G
    return TECNOLOGIA_2G  # net_type in NET_TYPE_2G, garantizado por el Validator


def normalize_record_csv(data: dict) -> dict:
    """Preserve CSV signal fields without inferring a different measurement."""
    def signal(name):
        value = data.get(name)
        return None if value is None else int(value)

    return {
        "timestamp_medicion": normalize_sys_time(data["sys_time"]),
        "cell_id": int(data["cid"]),
        "tac": None if data["lac_tac"] is None else int(data["lac_tac"]),
        "earfcn": None if data["arfcn"] is None else int(data["arfcn"]),
        "tecnologia": map_tecnologia_csv(data["net_type"]),
        # NULL cuando cleaner.apply_sentinels_csv anuló gps sin fix (ya no se
        # rechaza el registro completo por esto, ver validator.py).
        "latitud": None if data["lat"] is None else float(data["lat"]),
        "longitud": None if data["long"] is None else float(data["long"]),
        "rssi": signal("rssi"),
        "rsrp": signal("rssi_strongest"),
        "node_id": None if data["node_id"] is None else int(data["node_id"]),
        "psc_pci": None if data["psc_pci"] is None else int(data["psc_pci"]),
        "rsrq": None if data["rsrq"] is None else int(data["rsrq"]),
        "rssnr": None if data["rssnr"] is None else int(data["rssnr"]),
        "accuracy": None if data["accuracy"] is None else int(data["accuracy"]),
        # Identificadores crudos, además de cell_id/tac (ver comentario de
        # cell_id en schema.sql sobre la ambigüedad de identidad en LTE).
        "cid": int(data["cid"]),
        "lac_tac_raw": None if data["lac_tac"] is None else int(data["lac_tac"]),
        "report_index": int(data["report"]),
        "net_type": str(data["net_type"]),
        "tech": str(data["tech"]),
        "data_state": None if data["data_state"] is None else str(data["data_state"]),
        "call_state": None if data["call_state"] is None else str(data["call_state"]),
    }
