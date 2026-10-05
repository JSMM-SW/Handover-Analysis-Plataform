from datetime import datetime, timezone

from app.modules.ingesta.etl.transformer import structure_record


def test_structure_record_adds_origin_fields():
    normalized = {
        "timestamp_medicion": datetime(2026, 5, 6, 23, 49, 15, tzinfo=timezone.utc),
        "cell_id": 25949452,
        "tac": 50240,
        "earfcn": 740,
        "tecnologia": 1,
        "latitud": -0.290748,
        "longitud": -78.550426,
        "rssi": -94,
    }

    result = structure_record(
        normalized, hoja_origen=None, archivo_origen="Session.csv", origen_formato="csv"
    )

    assert result["hoja_origen"] == None
    assert result["archivo_origen"] == "Session.csv"
    assert result["origen_formato"] == "csv"
    assert result["cell_id"] == 25949452
    assert result["timestamp_medicion"] == normalized["timestamp_medicion"]
