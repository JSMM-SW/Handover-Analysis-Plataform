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
