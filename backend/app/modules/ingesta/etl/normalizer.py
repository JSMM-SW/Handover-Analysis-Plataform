"""Etapa Normalize: unifica formatos y convierte a los tipos/unidades del
formato estándar de salida (Objetivo 3 del plan de tesis).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.modules.ingesta.etl.constants import (
    NET_TYPE_3G,
    NET_TYPE_LTE,
    TECNOLOGIA_3G,
    TECNOLOGIA_LTE,
    TIMEZONE_ORIGEN,
)

_ORIGEN_TZ = ZoneInfo(TIMEZONE_ORIGEN)


def normalize_timestamp(fecha: int, hora: int) -> datetime:
    """Combina Fecha (AAAAMMDD) + Hora (HHMMSS) en un datetime UTC.

    Ambos valores vienen del Excel en hora local America/Guayaquil (UTC-5,
    sin horario de verano). `hora` se rellena con ceros a la izquierda
    porque las horas de un solo dígito (ej. 08:49:15) pierden el cero al
    leerse como entero.
    """
    fecha_str = str(fecha).zfill(8)
    hora_str = str(hora).zfill(6)

    local_dt = datetime(
        year=int(fecha_str[0:4]),
        month=int(fecha_str[4:6]),
        day=int(fecha_str[6:8]),
        hour=int(hora_str[0:2]),
        minute=int(hora_str[2:4]),
        second=int(hora_str[4:6]),
        tzinfo=_ORIGEN_TZ,
    )
    return local_dt.astimezone(timezone.utc)


def normalize_record(data: dict) -> dict:
    """Convierte un registro crudo (ya validado) a los tipos del dataset final."""
    return {
        "timestamp_medicion": normalize_timestamp(data["Fecha"], data["Hora"]),
        "cell_id": int(data["Cell ID/ECI"]),
        "tac": int(data["TAC/LAC"]),
        "earfcn": int(data["EARFCN"]),
        "tecnologia": int(data["Tecnología"]),
        "latitud": float(data["Latitud"]),
        "longitud": float(data["Longitud"]),
        "rsrp_dbm": int(data["RSRP"]),
    }


def normalize_sys_time(sys_time) -> datetime:
    """Parsea `sys_time` (formato AAAAMMDDHHMMSS, 14 dígitos) a datetime UTC.

    Mismo criterio de zona horaria que `normalize_timestamp` (hora local
    America/Guayaquil, UTC-5 sin DST), pero un parser distinto porque el
    formato de origen es un único entero/string de 14 dígitos en vez de dos
    campos separados.
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

    Asume que `net_type` ya fue validado como uno de los 3 valores
    confirmados (LTE, UMTS, HSPA+) por `validate_record_csv`; cualquier otro
    valor ya habría sido rechazado antes de llegar aquí.
    """
    if net_type == NET_TYPE_LTE:
        return TECNOLOGIA_LTE
    return TECNOLOGIA_3G  # net_type in NET_TYPE_3G, garantizado por el Validator


def normalize_record_csv(data: dict) -> dict:
    """Convierte un registro crudo de csv (ya validado y con centinelas
    nuleados por `cleaner.apply_sentinels_csv`) a los tipos del dataset
    final. `rsrp_dbm` es None: el csv no tiene un campo equivalente a RSRP
    (usa rssi/rsrq/rssnr en su lugar).
    """
    return {
        "timestamp_medicion": normalize_sys_time(data["sys_time"]),
        "cell_id": int(data["cid"]),
        "tac": None if data["lac_tac"] is None else int(data["lac_tac"]),
        "earfcn": None if data["arfcn"] is None else int(data["arfcn"]),
        "tecnologia": map_tecnologia_csv(data["net_type"]),
        "latitud": float(data["lat"]),
        "longitud": float(data["long"]),
        "rsrp_dbm": None,
        "node_id": None if data["node_id"] is None else int(data["node_id"]),
        "psc_pci": None if data["psc_pci"] is None else int(data["psc_pci"]),
        "rssi": None if data["rssi"] is None else int(data["rssi"]),
        "rsrq": None if data["rsrq"] is None else int(data["rsrq"]),
        "rssnr": None if data["rssnr"] is None else int(data["rssnr"]),
        "accuracy": None if data["accuracy"] is None else int(data["accuracy"]),
    }
