from app.modules.ingesta.etl.cleaner import apply_sentinels_csv, deduplicate
from app.modules.ingesta.etl.constants import (
    DEDUP_KEY_CSV,
)


def _raw_record(hoja, fila, **overrides):
    data = dict(sys_time=20260505084058, cid=192, lac_tac=33171, arfcn=740, net_type="LTE", lat=-0.18, long=-78.46)
    data.update(overrides)
    return {"hoja_origen": hoja, "fila_excel": fila, "data": data}


def test_deduplicate_keeps_first_and_flags_rest():
    first = _raw_record("Datos 1", 2)
    duplicate = _raw_record("Datos 2", 2)  # mismos 7 valores de negocio
    different = _raw_record("Datos 2", 3, sys_time=20260505084120)

    unique, duplicates = deduplicate([first, duplicate, different], DEDUP_KEY_CSV)

    assert unique == [first, different]
    assert duplicates == [duplicate]


def test_deduplicate_with_no_duplicates_returns_all_as_unique():
    a = _raw_record("Datos 1", 2)
    b = _raw_record("Datos 1", 3, sys_time=20260505084120)

    unique, duplicates = deduplicate([a, b], DEDUP_KEY_CSV)

    assert unique == [a, b]
    assert duplicates == []


def _csv_raw_record(**overrides) -> dict:
    data = {
        "sys_time": 20260505084058,
        "cid": 192,
        "lac_tac": 33171,
        "arfcn": 740,
        "net_type": "LTE",
        "lat": -0.180653,
        "long": -78.467838,
        "gps": 1,
        "node_id": 28886,
        "psc_pci": 61,
        "rssi": -90,
        "rsrq": -15,
        "rssnr": -9,
        "accuracy": 3,
    }
    data.update(overrides)
    return {"hoja_origen": None, "fila_excel": 2, "data": data}


def test_apply_sentinels_csv_nulls_only_flagged_fields():
    record = _csv_raw_record(rssnr=2147483647, psc_pci=2147483647)

    cleaned, nulled = apply_sentinels_csv(record["data"])

    assert cleaned["rssnr"] is None
    assert cleaned["psc_pci"] is None
    assert cleaned["cid"] == 192  # no tocado
    assert set(nulled) == {"rssnr", "psc_pci"}


def test_apply_sentinels_csv_handles_accuracy_own_sentinel():
    record = _csv_raw_record(accuracy=-1)

    cleaned, nulled = apply_sentinels_csv(record["data"])

    assert cleaned["accuracy"] is None
    assert "accuracy" in nulled


def test_apply_sentinels_csv_no_sentinels_returns_unchanged():
    record = _csv_raw_record()

    cleaned, nulled = apply_sentinels_csv(record["data"])

    assert cleaned == record["data"]
    assert nulled == []


def test_apply_sentinels_csv_does_not_mutate_original():
    record = _csv_raw_record(rssnr=2147483647)
    original = dict(record["data"])

    apply_sentinels_csv(record["data"])

    assert record["data"] == original


def test_apply_sentinels_csv_nulls_latlong_on_gps_zero():
    """Desde Session_43_20260623_165825.csv: gps=0 ya no rechaza el registro
    (ver validator.py), se anulan lat/long y se conserva el resto."""
    record = _csv_raw_record(gps=0, lat=-1, long=-1)

    cleaned, nulled = apply_sentinels_csv(record["data"])

    assert cleaned["lat"] is None
    assert cleaned["long"] is None
    assert cleaned["cid"] == 192  # no tocado
    assert "gps" in nulled


def test_apply_sentinels_csv_nulls_latlong_on_sentinel_even_if_gps_flag_is_one():
    """En los datos reales gps=0 y lat=long=-1 siempre coinciden, pero la
    regla verifica ambas condiciones de forma independiente por robustez."""
    record = _csv_raw_record(gps=1, lat=-1, long=-1)

    cleaned, nulled = apply_sentinels_csv(record["data"])

    assert cleaned["lat"] is None
    assert cleaned["long"] is None
    assert "gps" in nulled


def test_apply_sentinels_csv_keeps_latlong_when_gps_fix_present():
    record = _csv_raw_record(gps=1)

    cleaned, nulled = apply_sentinels_csv(record["data"])

    assert cleaned["lat"] == record["data"]["lat"]
    assert cleaned["long"] == record["data"]["long"]
    assert "gps" not in nulled


def test_deduplicate_csv_keeps_first_and_flags_rest():
    first = _csv_raw_record()
    duplicate = _csv_raw_record()
    different = _csv_raw_record(sys_time=20260505084059)

    unique, duplicates = deduplicate([first, duplicate, different], DEDUP_KEY_CSV)

    assert unique == [first, different]
    assert duplicates == [duplicate]
