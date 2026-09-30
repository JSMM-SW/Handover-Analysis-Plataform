from app.modules.ingesta.etl.cleaner import apply_sentinels_csv, deduplicate, validate_ranges
from app.modules.ingesta.etl.constants import (
    DEDUP_KEY_CSV,
    DEDUP_KEY_XLSX,
    MOTIVO_COORDENADAS_FUERA_DE_RANGO,
    MOTIVO_RSRP_FUERA_DE_RANGO,
)


def _record(**overrides) -> dict:
    base = {
        "Cell ID/ECI": 25949452,
        "RSRP": -94,
        "Latitud": -0.290748,
        "Longitud": -78.550426,
    }
    base.update(overrides)
    return base


def test_valid_ranges_pass():
    assert validate_ranges(_record()) is None


def test_strong_signal_within_bounds_is_not_rejected():
    """-29 dBm es inusualmente fuerte pero físicamente plausible: no se
    rechaza aquí (el warning se genera en la etapa de Normalize/pipeline)."""
    assert validate_ranges(_record(RSRP=-29)) is None


def test_rejects_rsrp_out_of_physical_range():
    assert validate_ranges(_record(RSRP=-141)) == MOTIVO_RSRP_FUERA_DE_RANGO


def test_rejects_coordinates_outside_ecuador():
    assert (
        validate_ranges(_record(Latitud=10, Longitud=-78.5))
        == MOTIVO_COORDENADAS_FUERA_DE_RANGO
    )


def _raw_record(hoja: str, fila: int, **data_overrides) -> dict:
    data = {
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
    data.update(data_overrides)
    return {"hoja_origen": hoja, "fila_excel": fila, "data": data}


def test_deduplicate_keeps_first_and_flags_rest():
    first = _raw_record("Datos 1", 2)
    duplicate = _raw_record("Datos 2", 2)  # mismos 9 valores de negocio
    different = _raw_record("Datos 2", 3, Hora=184920)

    unique, duplicates = deduplicate([first, duplicate, different], DEDUP_KEY_XLSX)

    assert unique == [first, different]
    assert duplicates == [duplicate]


def test_deduplicate_with_no_duplicates_returns_all_as_unique():
    a = _raw_record("Datos 1", 2)
    b = _raw_record("Datos 1", 3, Hora=184920)

    unique, duplicates = deduplicate([a, b], DEDUP_KEY_XLSX)

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


def test_deduplicate_csv_keeps_first_and_flags_rest():
    first = _csv_raw_record()
    duplicate = _csv_raw_record()
    different = _csv_raw_record(sys_time=20260505084059)

    unique, duplicates = deduplicate([first, duplicate, different], DEDUP_KEY_CSV)

    assert unique == [first, different]
    assert duplicates == [duplicate]
