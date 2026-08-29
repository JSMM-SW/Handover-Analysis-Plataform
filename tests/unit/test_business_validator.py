from app.etl.constants import MOTIVO_CELL_ID_CERO, MOTIVO_GPS_SIN_FIX, MOTIVO_RSRP_CENTINELA
from app.etl.validator import validate_record


def _record(**overrides) -> dict:
    base = {
        "Cell ID/ECI": 25949452,
        "RSRP": -94,
        "Latitud": -0.290748,
        "Longitud": -78.550426,
    }
    base.update(overrides)
    return base


def test_valid_record_passes():
    assert validate_record(_record()) is None


def test_rejects_cell_id_zero():
    assert validate_record(_record(**{"Cell ID/ECI": 0})) == MOTIVO_CELL_ID_CERO


def test_rejects_rsrp_sentinel():
    assert validate_record(_record(RSRP=99)) == MOTIVO_RSRP_CENTINELA


def test_rejects_gps_sin_fix():
    assert validate_record(_record(Latitud=0, Longitud=0)) == MOTIVO_GPS_SIN_FIX


def test_cell_id_zero_takes_precedence_over_rsrp_sentinel():
    """En los datos reales, cell_id=0 siempre trae también rsrp=99; el motivo
    reportado debe ser el más específico (cell_id), no el genérico (rsrp)."""
    record = _record(**{"Cell ID/ECI": 0, "RSRP": 99})
    assert validate_record(record) == MOTIVO_CELL_ID_CERO
