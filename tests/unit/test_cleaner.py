from app.modules.ingesta.etl.cleaner import deduplicate, validate_ranges
from app.modules.ingesta.etl.constants import (
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

    unique, duplicates = deduplicate([first, duplicate, different])

    assert unique == [first, different]
    assert duplicates == [duplicate]


def test_deduplicate_with_no_duplicates_returns_all_as_unique():
    a = _raw_record("Datos 1", 2)
    b = _raw_record("Datos 1", 3, Hora=184920)

    unique, duplicates = deduplicate([a, b])

    assert unique == [a, b]
    assert duplicates == []
