from datetime import datetime, timedelta, timezone

from app.modules.ingesta.etl.velocity import compute_velocities

BASE = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)


def _record(offset_seconds, lat, long, hoja_origen="Datos 1"):
    return {
        "timestamp_medicion": BASE + timedelta(seconds=offset_seconds),
        "latitud": lat,
        "longitud": long,
        "hoja_origen": hoja_origen,
    }


def test_first_record_of_session_is_null():
    records = [_record(0, -0.29, -78.55)]
    compute_velocities(records, [])
    assert records[0]["velocidad_kmh"] is None


def test_computes_plausible_velocity_between_consecutive_records():
    # ~111m en 10s (aprox 0.001 grados de latitud) -> ~40 km/h
    records = [_record(0, -0.290000, -78.550000), _record(10, -0.291000, -78.550000)]
    compute_velocities(records, [])
    assert records[0]["velocidad_kmh"] is None
    assert records[1]["velocidad_kmh"] is not None
    assert 30 < records[1]["velocidad_kmh"] < 50


def test_zero_time_difference_is_null():
    records = [_record(0, -0.29, -78.55), _record(0, -0.291, -78.55)]
    compute_velocities(records, [])
    assert records[1]["velocidad_kmh"] is None


def test_gps_reject_anchor_nulls_next_record():
    records = [_record(0, -0.290000, -78.550000), _record(10, -0.291000, -78.550000)]
    # rechazo por gps sin fix justo entre los dos, misma hoja
    gps_anchor = (BASE + timedelta(seconds=5), "Datos 1")

    warnings = compute_velocities(records, [gps_anchor])

    assert records[0]["velocidad_kmh"] is None  # sigue siendo el primero de su grupo
    assert records[1]["velocidad_kmh"] is None  # el anterior en el tiempo fue un rechazo gps
    assert warnings == []


def test_gps_reject_anchor_in_different_session_does_not_affect():
    records = [_record(0, -0.290000, -78.550000), _record(10, -0.291000, -78.550000)]
    gps_anchor = (BASE + timedelta(seconds=5), "Datos 2")  # otra hoja/sesión

    compute_velocities(records, [gps_anchor])

    assert records[1]["velocidad_kmh"] is not None


def test_different_sessions_do_not_interfere():
    records = [
        _record(0, -0.290000, -78.550000, hoja_origen="Datos 1"),
        _record(1, -0.500000, -79.000000, hoja_origen="Datos 2"),  # muy lejos, pero otra sesión
    ]
    compute_velocities(records, [])
    # Ambos son el primero de su propia sesión -> ambos None, no se calcula
    # una velocidad absurda cruzando sesiones.
    assert records[0]["velocidad_kmh"] is None
    assert records[1]["velocidad_kmh"] is None


def test_unusual_velocity_is_kept_with_warning():
    # ~11km en 10s -> ~4000 km/h, claramente > 200
    records = [_record(0, -0.290000, -78.550000), _record(10, -0.390000, -78.550000)]
    warnings = compute_velocities(records, [])

    assert records[1]["velocidad_kmh"] is not None
    assert records[1]["velocidad_kmh"] > 200
    assert len(warnings) == 1
    assert "velocidad inusual" in warnings[0]


def test_none_hoja_origen_groups_together_like_csv():
    """csv siempre tiene hoja_origen=None: deben agruparse entre sí (toda la
    sesión csv es un solo grupo), no tratarse cada una como su propio grupo."""
    records = [
        _record(0, -0.290000, -78.550000, hoja_origen=None),
        _record(10, -0.291000, -78.550000, hoja_origen=None),
    ]
    compute_velocities(records, [])
    assert records[0]["velocidad_kmh"] is None
    assert records[1]["velocidad_kmh"] is not None
