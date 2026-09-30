from app.modules.ingesta.etl.constants import MOTIVO_CID_CENTINELA
from app.modules.ingesta.etl.validator import validate_record_csv


def _record(**overrides) -> dict:
    base = {
        "cid": 192,
        "gps": 1,
        "lat": -0.180653,
        "long": -78.467838,
        "net_type": "LTE",
    }
    base.update(overrides)
    return base


def test_valid_record_passes():
    assert validate_record_csv(_record()) is None


def test_valid_record_umts_passes():
    assert validate_record_csv(_record(net_type="UMTS")) is None


def test_valid_record_hspa_plus_passes():
    assert validate_record_csv(_record(net_type="HSPA+")) is None


def test_valid_record_hspa_without_plus_passes():
    """Confirmado en Session_43_20260623_165825.csv (145 filas reales):
    'HSPA' sin '+' es un valor real distinto de 'HSPA+', ambos 3G."""
    assert validate_record_csv(_record(net_type="HSPA")) is None


def test_valid_record_edge_passes():
    assert validate_record_csv(_record(net_type="EDGE")) is None


def test_valid_record_gprs_passes():
    assert validate_record_csv(_record(net_type="GPRS")) is None


def test_rejects_cid_sentinel():
    assert validate_record_csv(_record(cid=2147483647)) == MOTIVO_CID_CENTINELA


def test_does_not_reject_gps_zero():
    """Desde Session_43_20260623_165825.csv: gps sin fix ya NO rechaza el
    registro (rechazarlo tiraba el 92% del archivo real). El registro se
    conserva; es `cleaner.apply_sentinels_csv` quien anula lat/long."""
    assert validate_record_csv(_record(gps=0)) is None


def test_does_not_reject_latlong_sentinel_even_if_gps_flag_is_one():
    """En los datos reales gps=0 y lat=long=-1 siempre coinciden, pero por
    robustez el registro tampoco se rechaza si solo lat/long traen el
    centinela con gps=1 — la anulación a NULL vive en cleaner.py."""
    assert validate_record_csv(_record(gps=1, lat=-1, long=-1)) is None


def test_cid_centinela_rejects_even_with_gps_sin_fix():
    record = _record(cid=2147483647, gps=0)
    assert validate_record_csv(record) == MOTIVO_CID_CENTINELA


def test_rejects_unknown_net_type():
    motivo = validate_record_csv(_record(net_type="GSM"))
    assert motivo is not None
    assert "GSM" in motivo


def test_rejects_net_type_literally_unknown():
    """Caso real confirmado en Session_43_20260623_165825.csv (45 filas,
    0.05%): la propia app reporta net_type='UNKNOWN'. Se rechaza en vez de
    adivinar una tecnología, igual que cualquier otro valor no confirmado."""
    motivo = validate_record_csv(_record(net_type="UNKNOWN"))
    assert motivo is not None
    assert "UNKNOWN" in motivo
