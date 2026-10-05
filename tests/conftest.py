import io
import pytest


CSV_COLUMNS = [
    "sys_time",
    "lat",
    "long",
    "accuracy",
    "node_id",
    "cid",
    "psc_pci",
    "rssi",
    "rsrq",
    "rssnr",
    "gps",
    "lac_tac",
    "arfcn",
    "net_type",
    # Agregadas al soportar Session_43_20260623_165825.csv: siempre estuvieron
    # en los archivos reales, solo no se extraían antes de tener uso para ellas.
    "report",
    "tech",
    "data_state",
    "call_state",
]


@pytest.fixture
def sample_handover_csv_bytes() -> bytes:
    """CSV con delimitador ';' (como los archivos de sesión individual reales),
    con una mezcla de filas conocidas: una válida LTE, una válida UMTS (tech
    WCDMA) con rssnr centinela (se guarda con warning, no se rechaza), una con
    cid centinela (se rechaza), una GSM/GPRS con gps sin fix (ya NO se
    rechaza desde Session_43: se conserva con latitud/longitud NULL), y un
    duplicado exacto de la primera.
    """
    SENTINEL = 2147483647
    valid_lte_row = [
        20260505084058, -0.180653, -78.467838, 3, 28886, 192, 61, -90, -15, -9, 1, 33171, 740, "LTE",
        0, "LTE", "CONNECTED", "IDLE",
    ]
    valid_umts_with_rssnr_sentinel_row = [
        20260505084100, -0.180700, -78.467900, 5, 11, 29296, 476, -79, -12, SENTINEL, 1, 33171, 850, "UMTS",
        1, "WCDMA", "CONNECTED", "IDLE",
    ]
    cid_sentinel_row = [
        20260505084101, -0.180750, -78.467950, 3, SENTINEL, SENTINEL, 476, -100, -12, SENTINEL, 1, 65535, 850, "LTE",
        2, "LTE", "DISCONNECTED", "IDLE",
    ]
    # tech=GSM/net_type=GPRS (tecnologia=3) a propósito, distinto de LTE/UMTS,
    # para que valid_by_tecnologia no colisione en el test que consume esto:
    # ya no se rechaza por gps sin fix, así que sobrevive como fila válida.
    gps_sin_fix_row = [
        20260505084102, -1, -1, -1, 28886, 209, 61, -107, -13, SENTINEL, 0, 33171, 740, "GPRS",
        3, "GSM", "DISCONNECTED", "IDLE",
    ]
    rows = [
        CSV_COLUMNS,
        valid_lte_row,
        valid_umts_with_rssnr_sentinel_row,
        cid_sentinel_row,
        gps_sin_fix_row,
        valid_lte_row,  # duplicado exacto de la primera fila
    ]
    lines = [";".join(str(v) for v in row) for row in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")
