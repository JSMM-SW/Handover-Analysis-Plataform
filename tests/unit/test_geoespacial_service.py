from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.visualizacion_geoespacial.services import prepare_map
from app.modules.visualizacion_temporal.detector import Medicion, detectar_handovers


def temporal_events(rows):
    return detectar_handovers([Medicion(
        id_medicion=str(row.id_registro), sesion_id=str(getattr(row, 'execution_id', 'test-session')),
        timestamp_medicion=row.timestamp_medicion, cid=row.cell_id,
        node_id=getattr(row, 'node_id', None), tech={1: 'LTE', 2: 'WCDMA', 3: 'GSM'}.get(row.tecnologia),
        lac_tac=getattr(row, 'tac', None), report_index=index,
    ) for index, row in enumerate(rows)])


def point(seconds, **changes):
    values = dict(id_registro=uuid4(), timestamp_medicion=datetime(2026, 5, 5, tzinfo=timezone.utc) + timedelta(seconds=seconds),
                  latitud=-0.2, longitud=-78.5, cell_id=10, tecnologia=1, rsrp_dbm=-95, hoja_origen="Datos 1")
    return SimpleNamespace(**(values | changes))


def test_filters_do_not_bridge_excluded_measurements():
    rows = [point(0), point(1), point(2, cell_id=20), point(3), point(4)]
    result = prepare_map(rows, cell_id=10)
    assert result.total == 4
    assert result.tramos == [[rows[0].id_registro, rows[1].id_registro], [rows[3].id_registro, rows[4].id_registro]]


def test_hour_window_applies_to_each_day_in_ecuador_without_bridging_routes():
    rows = [point(13 * 3600), point(14 * 3600), point(86400 + 13 * 3600), point(86400 + 14 * 3600)]
    result = prepare_map(rows, hora_inicio=time(8), hora_fin=time(8, 59, 59))
    assert [p.id_registro for p in result.mediciones] == [rows[0].id_registro, rows[2].id_registro]
    assert result.tramos == []


def test_hour_filter_keeps_previous_observation_as_handover_context():
    rows = [point(13 * 3600 - 2, node_id=100), point(13 * 3600 - 1, node_id=100),
            point(13 * 3600, node_id=200, cell_id=20), point(13 * 3600 + 1, node_id=200, cell_id=20)]
    result = prepare_map(rows, hora_inicio=time(8), hora_fin=time(8, 0, 59), detected_events=temporal_events(rows))
    assert result.total == 2
    assert result.total_handovers == 1


@pytest.mark.parametrize('coordinates', [(None, None), (None, -78.5), (-0.2, None)])
def test_missing_gps_breaks_route_without_discarding_radio_context(coordinates):
    rows = [point(0, node_id=100), point(1, node_id=100),
            point(2, node_id=200, cell_id=20, latitud=coordinates[0], longitud=coordinates[1]),
            point(3, node_id=200, cell_id=20), point(4, node_id=300, cell_id=30)]
    result = prepare_map(rows, detected_events=temporal_events(rows))
    assert result.total == 4
    assert result.tramos == [[rows[0].id_registro, rows[1].id_registro],
                             [rows[3].id_registro, rows[4].id_registro]]
    assert result.total_handovers == 1
    assert result.handovers == []
    assert result.handovers_sin_ubicacion == 1


def test_session_without_gps_returns_empty_map():
    result = prepare_map([point(0, latitud=None, longitud=None)])
    assert result.total == result.total_handovers == 0
    assert result.tramos == []
    assert result.radios_base == []


def test_breaks_at_time_gaps_and_sheet_boundaries():
    rows = [point(0), point(1), point(90), point(91), point(92, hoja_origen="Datos 2")]
    result = prepare_map(rows)
    assert result.tramos == [[rows[0].id_registro, rows[1].id_registro], [rows[2].id_registro, rows[3].id_registro]]


def test_tied_timestamps_are_visible_but_not_connected():
    rows = [point(0), point(1), point(1), point(2)]
    result = prepare_map(rows)
    assert result.total == 4
    assert result.tramos == []
    assert any("repetidas" in warning for warning in result.advertencias)


def test_combines_technology_cell_and_bbox_filters():
    rows = [point(0), point(1, tecnologia=0), point(2, longitud=-79), point(3, cell_id=20)]
    result = prepare_map(rows, tecnologia=1, cell_id=10, bbox=(-78.6, -0.3, -78.4, -0.1))
    assert [p.id_registro for p in result.mediciones] == [rows[0].id_registro]


def test_empty_and_overflow():
    assert prepare_map([]).total == 0
    with pytest.raises(ValueError, match="50.000"):
        prepare_map([point(0)] * 50001)


def test_accepts_exactly_fifty_thousand_measurements():
    rows = [point(index) for index in range(50000)]
    result = prepare_map(rows)
    assert result.total == 50000
    assert result.tramos == [[row.id_registro for row in rows]]


def test_overlapping_sheets_keep_independent_routes():
    a, b = point(0), point(1)
    c, d = point(0, hoja_origen="Datos 2"), point(1, hoja_origen="Datos 2")
    result = prepare_map([a, c, b, d])
    assert result.total == 4
    assert result.tramos == [[a.id_registro, b.id_registro], [c.id_registro, d.id_registro]]


def test_overlapping_sessions_keep_independent_routes_and_handovers():
    first, second = uuid4(), uuid4()
    a = point(0, execution_id=first, node_id=100)
    b = point(1, execution_id=first, cell_id=20, node_id=200)
    c = point(0, execution_id=second, node_id=300)
    d = point(1, execution_id=second, cell_id=30, node_id=400)
    a2, b2 = point(0.5, execution_id=first, node_id=100), point(1.5, execution_id=first, cell_id=20, node_id=200)
    c2, d2 = point(0.5, execution_id=second, node_id=300), point(1.5, execution_id=second, cell_id=30, node_id=400)
    rows = [a, c, a2, c2, b, d, b2, d2]
    result = prepare_map(rows, detected_events=temporal_events(rows))
    assert {tuple(segment) for segment in result.tramos} == {(a.id_registro, a2.id_registro, b.id_registro, b2.id_registro), (c.id_registro, c2.id_registro, d.id_registro, d2.id_registro)}
    assert {event.id_registro for event in result.handovers} == {b.id_registro, d.id_registro}


def test_temporal_detects_same_node_and_same_cid_transitions():
    rows = [point(0, cell_id=10, node_id=100), point(1, cell_id=10, node_id=100),
            point(2, cell_id=20, node_id=100), point(3, cell_id=20, node_id=100),
            point(4, cell_id=20, node_id=200), point(5, cell_id=20, node_id=200)]
    result = prepare_map(rows, detected_events=temporal_events(rows))
    assert result.total_handovers == result.handovers_con_ubicacion == 2
    event = result.handovers[0]
    assert event.id_registro == rows[2].id_registro
    assert (event.celda_origen, event.nodo_origen, event.cell_id, event.node_id) == (10, 100, 20, 100)


@pytest.mark.parametrize('destination_seconds', [32, 90])
def test_temporal_discards_transitions_with_gaps_over_thirty_seconds(destination_seconds):
    rows = [point(0, node_id=100), point(1, node_id=100),
            point(destination_seconds, node_id=200, cell_id=20), point(destination_seconds + 1, node_id=200, cell_id=20)]
    assert prepare_map(rows, detected_events=temporal_events(rows)).total_handovers == 0


def test_temporal_does_not_count_a_single_sample_cell():
    rows = [point(0), point(1), point(2, cell_id=20), point(3), point(4)]
    assert prepare_map(rows, detected_events=temporal_events(rows)).total_handovers == 0


def test_filters_do_not_invent_or_hide_boundary_events():
    rows = [point(0, node_id=100, cell_id=10, longitud=-79), point(1, node_id=100, cell_id=10, longitud=-79),
            point(2, node_id=200, cell_id=20), point(3, node_id=200, cell_id=20), point(4, node_id=200, cell_id=30)]
    result = prepare_map(rows, bbox=(-78.6, -0.3, -78.4, -0.1), desde=rows[2].timestamp_medicion, detected_events=temporal_events(rows))
    assert result.total == 3
    assert result.total_handovers == 1
    assert result.handovers[0].registro_anterior_id == rows[1].id_registro
    assert prepare_map(rows, cell_id=30, detected_events=temporal_events(rows)).total_handovers == 0


def test_all_events_without_gps_still_count():
    rows = [point(index, cell_id=10 if index < 2 else 20, node_id=100, latitud=None, longitud=None) for index in range(4)]
    result = prepare_map(rows, detected_events=temporal_events(rows))
    assert result.total == 0
    assert result.total_handovers == result.handovers_sin_ubicacion == 1
    assert result.handovers_con_ubicacion == 0


def test_wcdma_handover_without_node_can_be_mapped():
    rows = [point(index, cell_id=10 if index < 2 else 20, tecnologia=2, tac=100, node_id=None) for index in range(4)]
    result = prepare_map(rows, detected_events=temporal_events(rows))
    assert result.total_handovers == 1
    assert result.handovers[0].nodo_origen is None
