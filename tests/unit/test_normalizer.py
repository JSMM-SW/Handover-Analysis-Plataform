from datetime import datetime, timezone

from app.modules.ingesta.etl.normalizer import normalize_record, normalize_timestamp


def test_normalize_timestamp_converts_local_to_utc():
    # 2026-05-06 18:49:15 America/Guayaquil (UTC-5) -> 2026-05-06 23:49:15 UTC
    result = normalize_timestamp(20260506, 184915)
    assert result == datetime(2026, 5, 6, 23, 49, 15, tzinfo=timezone.utc)


def test_normalize_timestamp_pads_single_digit_hour():
    # Hora "084915" pierde el cero inicial al leerse como entero (84915).
    result = normalize_timestamp(20260506, 84915)
    assert result == datetime(2026, 5, 6, 13, 49, 15, tzinfo=timezone.utc)


def test_normalize_record_maps_all_fields():
    raw = {
        "Fecha": 20260506,
        "Hora": 184915,
        "Cell ID/ECI": 25949452,
        "TAC/LAC": 50240,
        "EARFCN": 740,
        "Tecnología": 1,
        "Latitud": -0.290748,
        "Longitud": -78.550426,
        "RSRP": -94,
    }

    normalized = normalize_record(raw)

    assert normalized["cell_id"] == 25949452
    assert normalized["tac"] == 50240
    assert normalized["earfcn"] == 740
    assert normalized["tecnologia"] == 1
    assert normalized["latitud"] == -0.290748
    assert normalized["longitud"] == -78.550426
    assert normalized["rsrp_dbm"] == -94
    assert normalized["timestamp_medicion"] == datetime(2026, 5, 6, 23, 49, 15, tzinfo=timezone.utc)
