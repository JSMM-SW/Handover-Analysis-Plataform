from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.visualizacion_geoespacial.services import prepare_map


def point(seconds, **changes):
    values = dict(id_registro=uuid4(), timestamp_medicion=datetime(2026, 5, 5, tzinfo=timezone.utc) + timedelta(seconds=seconds),
                  latitud=-0.2, longitud=-78.5, cell_id=10, tecnologia=1, rsrp_dbm=-95, hoja_origen="Datos 1")
    return SimpleNamespace(**(values | changes))


def test_filters_do_not_bridge_excluded_measurements():
    rows = [point(0), point(1), point(2, cell_id=20), point(3), point(4)]
    result = prepare_map(rows, cell_id=10)
    assert result.total == 4
    assert result.tramos == [[rows[0].id_registro, rows[1].id_registro], [rows[3].id_registro, rows[4].id_registro]]


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
    with pytest.raises(ValueError, match="20.000"):
        prepare_map([point(0)] * 20001)


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
    result = prepare_map([a, c, b, d])
    assert {tuple(segment) for segment in result.tramos} == {(a.id_registro, b.id_registro), (c.id_registro, d.id_registro)}
    assert {event.id_registro for event in result.handovers} == {b.id_registro, d.id_registro}


def test_handover_requires_both_cell_and_node_change():
    rows = [point(0, cell_id=10, node_id=100), point(1, cell_id=20, node_id=100),
            point(2, cell_id=20, node_id=200), point(3, cell_id=30, node_id=300)]
    result = prepare_map(rows)
    assert result.total_handovers == 1
    event = result.handovers[0]
    assert event.id_registro == rows[3].id_registro
    assert (event.celda_origen, event.nodo_origen, event.cell_id, event.node_id) == (20, 200, 30, 300)


@pytest.mark.parametrize('changes', [dict(node_id=None), dict(node_id=2147483647),
                                    dict(hoja_origen='Otra'), dict(timestamp_medicion=point(90).timestamp_medicion),
                                    dict(timestamp_medicion=point(0).timestamp_medicion)])
def test_ambiguous_or_disconnected_records_are_not_handovers(changes):
    assert prepare_map([point(0, node_id=100), point(1, **(dict(node_id=200, cell_id=20) | changes))]).total_handovers == 0


def test_filters_do_not_invent_or_hide_boundary_events():
    rows = [point(0, node_id=100, cell_id=10, longitud=-79),
            point(1, node_id=200, cell_id=20), point(2, node_id=200, cell_id=30)]
    result = prepare_map(rows, bbox=(-78.6, -0.3, -78.4, -0.1), desde=rows[1].timestamp_medicion)
    assert result.total == 2
    assert result.total_handovers == 1
    assert result.handovers[0].registro_anterior_id == rows[0].id_registro
    assert prepare_map(rows, cell_id=30).total_handovers == 0
