from datetime import datetime, timezone

from app.modules.ingesta.etl.normalizer import (
    map_tecnologia_csv,
    normalize_record_csv,
    normalize_sys_time,
)


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


def test_map_tecnologia_csv_wcdma():
    assert map_tecnologia_csv("WCDMA") == 2


def test_map_tecnologia_csv_gsm():
    assert map_tecnologia_csv("GSM") == 3


def test_tecnologia_follows_tech_not_net_type():
    """Session_41..47: net_type=HSPA con tech=LTE (band 700/1900, EARFCN,
    rsrq y node_id presentes) es una celda LTE; tecnologia debe ser 1 y
    net_type se conserva tal cual como dato informativo."""
    record = normalize_record_csv({
        "sys_time": 20260620182003, "cid": 191, "lac_tac": 33171, "arfcn": 700,
        "net_type": "HSPA", "tech": "LTE", "lat": None, "long": None, "rssi": -114,
        "node_id": 28953, "psc_pci": 436, "rsrq": -21, "rssnr": None, "accuracy": None,
        "report": 0, "data_state": "CONNECTED", "call_state": "IDLE",
    })
    assert record["tecnologia"] == 1
    assert record["rssi"] == -114
    assert record["net_type"] == "HSPA"


def test_normalize_record_csv_maps_all_fields_lte():
    # Valores representativos de dataset_unificado.csv (misma fila usada en
    # cid/lac_tac/node_id/psc_pci/rssi/rsrq que la primera fila real de
    # Session_5), sin centinelas.
    raw = {
        "sys_time": 20260505084058,
        "report": 5,
        "cid": 192,
        "lac_tac": 33171,
        "arfcn": 740,
        "net_type": "LTE",
        "tech": "LTE",
        "data_state": "CONNECTED",
        "call_state": "IDLE",
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
    assert normalized["rssi"] == -90  # rssi se conserva tal cual, sin reparto por tech
    assert normalized["node_id"] == 28886
    assert normalized["psc_pci"] == 61
    assert normalized["rsrq"] == -15
    assert normalized["rssnr"] == -9
    assert normalized["accuracy"] == 3
    assert normalized["cid"] == 192
    assert normalized["lac_tac_raw"] == 33171
    assert normalized["report_index"] == 5
    assert normalized["net_type"] == "LTE"
    assert normalized["tech"] == "LTE"
    assert normalized["data_state"] == "CONNECTED"
    assert normalized["call_state"] == "IDLE"


def test_normalize_record_csv_preserves_rssi_for_wcdma_and_gsm():
    base = {
        "sys_time": 20260505084058,
        "report": 1,
        "lac_tac": 33171,
        "arfcn": None,
        "lat": -0.18,
        "long": -78.46,
        "node_id": None,
        "psc_pci": None,
        "rsrq": None,
        "rssnr": None,
        "accuracy": None,
        "data_state": "DISCONNECTED",
        "call_state": "IDLE",
    }

    wcdma = normalize_record_csv({**base, "cid": 30405, "net_type": "HSPA", "tech": "WCDMA", "rssi": -102})
    assert wcdma["rssi"] == -102
    assert wcdma["tecnologia"] == 2

    gsm = normalize_record_csv({**base, "cid": 21433, "net_type": "GPRS", "tech": "GSM", "rssi": -95})
    assert gsm["rssi"] == -95
    assert gsm["tecnologia"] == 3


def test_normalize_record_csv_passes_through_nulled_sentinels():
    # Tal como los deja cleaner.apply_sentinels_csv antes de llegar aquí.
    raw = {
        "sys_time": 20260505084058,
        "report": 5,
        "cid": 28886,
        "lac_tac": None,
        "arfcn": None,
        "net_type": "LTE",
        "tech": "LTE",
        "data_state": "DISCONNECTED",
        "call_state": "IDLE",
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
    assert normalized["lac_tac_raw"] is None


def test_normalize_record_csv_nulls_latlong_when_gps_sin_fix():
    """Tal como los deja cleaner.apply_sentinels_csv cuando gps sin fix (ya
    no rechaza el registro, ver validator.py). No debe intentar float(None)."""
    raw = {
        "sys_time": 20260505084058,
        "report": 7,
        "cid": 192,
        "lac_tac": 33171,
        "arfcn": 740,
        "net_type": "LTE",
        "tech": "LTE",
        "data_state": "CONNECTED",
        "call_state": "IDLE",
        "lat": None,
        "long": None,
        "node_id": None,
        "psc_pci": None,
        "rssi": -90,
        "rsrq": None,
        "rssnr": None,
        "accuracy": None,
    }

    normalized = normalize_record_csv(raw)

    assert normalized["latitud"] is None
    assert normalized["longitud"] is None
    assert normalized["cid"] == 192  # resto del registro se conserva
