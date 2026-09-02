"""Etapa Normalize: unifica formatos y convierte a los tipos/unidades del
formato estándar de salida (Objetivo 3 del plan de tesis).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.etl.constants import TIMEZONE_ORIGEN

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
