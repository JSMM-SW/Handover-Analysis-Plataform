from app.modules.ingesta.etl.constants import MOTIVO_CID_CENTINELA, MOTIVO_TECNOLOGIA_AUSENTE
from app.modules.ingesta.etl.validator import validate_record_csv


def _record(**overrides) -> dict:
    base = {
        "cid": 192,
        "gps": 1,
        "lat": -0.180653,
        "long": -78.467838,
        "net_type": "LTE",
        "tech": "LTE",
    }
    base.update(overrides)
    return base


def test_valid_record_passes():
    assert validate_record_csv(_record()) is None


def test_valid_record_wcdma_passes():
    assert validate_record_csv(_record(tech="WCDMA", net_type="HSPA")) is None


def test_valid_record_gsm_passes():
    assert validate_record_csv(_record(tech="GSM", net_type="EDGE")) is None


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


def test_net_type_unknown_no_longer_rejects():
    """Session_41..47: 575 filas con net_type='UNKNOWN' traen tech y señal
    válidos. Con `tech` como fuente de `tecnologia`, net_type es informativo
    y ya no es motivo de rechazo."""
    assert validate_record_csv(_record(net_type="UNKNOWN")) is None


def test_net_type_disagreeing_with_tech_does_not_reject():
    """Caso real (S45: 10,520 filas): net_type=HSPA con tech=LTE."""
    assert validate_record_csv(_record(net_type="HSPA", tech="LTE")) is None


def test_rejects_unknown_tech():
    motivo = validate_record_csv(_record(tech="NR"))
    assert motivo is not None
    assert "NR" in motivo


def test_rejects_empty_tech():
    assert validate_record_csv(_record(tech=None)) == MOTIVO_TECNOLOGIA_AUSENTE
