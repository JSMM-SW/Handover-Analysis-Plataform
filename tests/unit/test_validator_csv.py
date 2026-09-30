from app.modules.ingesta.etl.constants import MOTIVO_CID_CENTINELA, MOTIVO_GPS_SIN_FIX_CSV
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


def test_rejects_cid_sentinel():
    assert validate_record_csv(_record(cid=2147483647)) == MOTIVO_CID_CENTINELA


def test_rejects_gps_zero():
    assert validate_record_csv(_record(gps=0)) == MOTIVO_GPS_SIN_FIX_CSV


def test_rejects_latlong_sentinel_even_if_gps_flag_is_one():
    """En los datos reales gps=0 y lat=long=-1 siempre coinciden, pero la
    regla exige verificar ambas condiciones de forma independiente."""
    assert validate_record_csv(_record(gps=1, lat=-1, long=-1)) == MOTIVO_GPS_SIN_FIX_CSV


def test_cid_sentinel_takes_precedence_over_gps_sin_fix():
    record = _record(cid=2147483647, gps=0)
    assert validate_record_csv(record) == MOTIVO_CID_CENTINELA


def test_rejects_unknown_net_type():
    motivo = validate_record_csv(_record(net_type="GSM"))
    assert motivo is not None
    assert "GSM" in motivo
