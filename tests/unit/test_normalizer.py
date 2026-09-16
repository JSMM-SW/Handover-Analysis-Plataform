from datetime import datetime, timezone

from app.modules.ingesta.etl.normalizer import (
    map_tecnologia_csv,
    normalize_record,
    normalize_record_csv,
    normalize_sys_time,
    normalize_timestamp,
)


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


def test_normalize_sys_time_converts_local_to_utc():
    # 2026-05-05 12:34:21 America/Guayaquil (UTC-5) -> 17:34:21 UTC
    # (valor real de dataset_unificado.csv).
    result = normalize_sys_time(20260505123421)
    assert result == datetime(2026, 5, 5, 17, 34, 21, tzinfo=timezone.utc)


def test_normalize_sys_time_accepts_string_input():
    # pandas puede entregar sys_time como numpy.int64; str(int(...)) debe
    # normalizarlo igual que un int nativo.
    result = normalize_sys_time("20260505123421")
    assert result == datetime(2026, 5, 5, 17, 34, 21, tzinfo=timezone.utc)


def test_map_tecnologia_csv_lte():
    assert map_tecnologia_csv("LTE") == 1


def test_map_tecnologia_csv_umts():
    assert map_tecnologia_csv("UMTS") == 2


def test_map_tecnologia_csv_hspa_plus():
    assert map_tecnologia_csv("HSPA+") == 2


def test_normalize_record_csv_maps_all_fields_lte():
    # Valores representativos de dataset_unificado.csv (misma fila usada en
    # cid/lac_tac/node_id/psc_pci/rssi/rsrq que la primera fila real de
    # Session_5), sin centinelas.
    raw = {
        "sys_time": 20260505084058,
        "cid": 192,
        "lac_tac": 33171,
        "arfcn": 740,
        "net_type": "LTE",
        "lat": -0.180653,
        "long": -78.467838,
        "node_id": 28886,
        "psc_pci": 61,
        "rssi": -90,
        "rsrq": -15,
        "rssnr": -9,
        "accuracy": 3,
    }

    normalized = normalize_record_csv(raw)

    assert normalized["cell_id"] == 192
    assert normalized["tac"] == 33171
    assert normalized["earfcn"] == 740
    assert normalized["tecnologia"] == 1
    assert normalized["latitud"] == -0.180653
    assert normalized["longitud"] == -78.467838
    assert normalized["rsrp_dbm"] is None  # csv no tiene equivalente de RSRP
    assert normalized["node_id"] == 28886
    assert normalized["psc_pci"] == 61
    assert normalized["rssi"] == -90
    assert normalized["rsrq"] == -15
    assert normalized["rssnr"] == -9
    assert normalized["accuracy"] == 3


def test_normalize_record_csv_passes_through_nulled_sentinels():
    # Tal como los deja cleaner.apply_sentinels_csv antes de llegar aquí.
    raw = {
        "sys_time": 20260505084058,
        "cid": 28886,
        "lac_tac": None,
        "arfcn": None,
        "net_type": "LTE",
        "lat": -0.180653,
        "long": -78.467838,
        "node_id": None,
        "psc_pci": None,
        "rssi": None,
        "rsrq": None,
        "rssnr": None,
        "accuracy": None,
    }

    normalized = normalize_record_csv(raw)

    assert normalized["tac"] is None
    assert normalized["earfcn"] is None
    assert normalized["node_id"] is None
    assert normalized["psc_pci"] is None
    assert normalized["rssi"] is None
    assert normalized["rsrq"] is None
    assert normalized["rssnr"] is None
    assert normalized["accuracy"] is None
