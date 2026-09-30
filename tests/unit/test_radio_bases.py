from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.modules.visualizacion_geoespacial.radio_bases import estimate_radio_bases
from app.modules.visualizacion_geoespacial.schemas import Measurement
from app.modules.visualizacion_geoespacial.services import prepare_map

SESSION = UUID('00000000-0000-0000-0000-000000000001')


def measurements(count=5, **overrides):
    return [Measurement(**(dict(
        id_registro=uuid4(), execution_id=SESSION,
        timestamp_medicion=datetime(2026, 5, 5, 13, tzinfo=timezone.utc) + timedelta(seconds=i),
        latitud=-0.2 + i * 0.001, longitud=-78.5, cell_id=10, node_id=100,
        tecnologia=1, rssi=-80, accuracy=5, psc_pci=0, earfcn=1700,
        tac=1, hoja_origen=None, rsrp_dbm=None,
    ) | overrides)) for i in range(count)]


def test_equal_weights_give_arithmetic_center_and_optional_pci_zero_is_valid():
    points = measurements()
    stations, summary = estimate_radio_bases(points)
    assert len(stations) == 1
    station = stations[0]
    assert station.latitud == pytest.approx(-0.198, abs=1e-7)
    assert station.longitud == -78.5
    assert station.psc_pci == [0]
    assert station.posiciones_utilizadas == 5
    assert station.dispersion_m > 0
    assert summary.grupos_insuficientes == 0


def test_signal_and_accuracy_weights_match_formula():
    points = measurements()
    points[0].rssi = -70
    points[1].accuracy = 10
    weights = [1/25, 0.1/100, 0.1/25, 0.1/25, 0.1/25]
    expected = sum(w * p.latitud for w, p in zip(weights, points)) / sum(weights)
    stations, _ = estimate_radio_bases(points)
    assert stations[0].latitud == pytest.approx(expected, abs=1e-7)


def test_duplicates_and_long_stop_do_not_pull_center_or_depend_on_input_order():
    points = measurements()
    expected, _ = estimate_radio_bases(points)
    repeated = points + [points[0].model_copy(update={'id_registro': uuid4(), 'timestamp_medicion': points[-1].timestamp_medicion}) for _ in range(100)]
    actual, summary = estimate_radio_bases(list(reversed(repeated)))
    assert actual == expected
    assert summary.duplicados_descartados == 100


@pytest.mark.parametrize('field,value', [
    ('execution_id', uuid4()), ('node_id', 200), ('cell_id', 20),
    ('tecnologia', 2), ('earfcn', 1800), ('hoja_origen', 'Otro recorrido'), ('tac', 2),
])
def test_session_and_cell_identity_groups_are_independent(field, value):
    points = measurements() + measurements(**{field: value})
    stations, summary = estimate_radio_bases(points)
    assert len(stations) == 2
    assert len({p.id for p in stations}) == 2
    assert summary.grupos_evaluados == 2


@pytest.mark.parametrize('overrides', [
    {'execution_id': None}, {'node_id': None}, {'node_id': 2147483647},
    {'cell_id': 0}, {'tecnologia': 0}, {'earfcn': None}, {'rssi': None}, {'rssi': 2147483647},
    {'accuracy': None}, {'accuracy': 0}, {'accuracy': 51},
    {'latitud': 0, 'longitud': 0}, {'latitud': float('nan')},
])
def test_unusable_measurements_do_not_create_fake_stations(overrides):
    stations, summary = estimate_radio_bases(measurements(**overrides))
    assert not stations
    assert summary.mediciones_descartadas == 5
    assert sum(summary.motivos.values()) == 5


def test_missing_pci_does_not_block_estimation():
    stations, _ = estimate_radio_bases(measurements(psc_pci=None))
    assert len(stations) == 1
    assert stations[0].psc_pci == []


def test_insufficient_positions_or_extent_are_omitted():
    for points in (measurements(4), measurements(10, latitud=-0.2),
                   [p.model_copy(update={'latitud': -0.2 + i * 0.00001}) for i, p in enumerate(measurements())],
                   [p.model_copy(update={'latitud': -0.2 + i}) for i, p in enumerate(measurements())]):
        stations, summary = estimate_radio_bases(points)
        assert not stations
        assert summary.grupos_insuficientes == 1


def test_strongest_fraction_keeps_ties_without_arbitrary_direction_bias():
    points = measurements(50)
    for i, point in enumerate(points):
        point.rssi = -60 if i < 10 else -90
    stations, _ = estimate_radio_bases(points)
    assert stations[0].posiciones_utilizadas == 10
    assert stations[0].latitud == pytest.approx(-0.1955, abs=1e-7)
    stations, _ = estimate_radio_bases(measurements(50))
    assert stations[0].posiciones_utilizadas == 50


def test_map_filters_and_boundary_context_apply_before_estimation():
    points = measurements()
    assert len(prepare_map(points).radios_base) == 1
    assert not prepare_map(points, desde=points[1].timestamp_medicion).radios_base
    assert not prepare_map(points, tecnologia=2).radios_base
    assert not prepare_map(points, bbox=(-78.6, -0.198, -78.4, -0.195)).radios_base
    assert not prepare_map([]).radios_base
