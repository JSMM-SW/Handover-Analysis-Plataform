from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app
from app.modules.visualizacion_geoespacial.router import get_repository
from app.shared.db.database import get_db


@pytest.fixture
def geo_client():
    execution_id = uuid4()
    calls = []

    class Repository:
        def execution(self, key):
            return object() if key == execution_id else None

        def sheets(self, key):
            return ["Datos 1", None]

        def measurements(self, keys, sheet, start, end):
            calls.append((keys, sheet, start, end))
            return [SimpleNamespace(id_registro=uuid4(), timestamp_medicion=datetime(2026, 5, 5, 13, tzinfo=timezone.utc),
                                    latitud=-0.2, longitud=-78.5, cell_id=10, tecnologia=2 if sheet is None else 1, rsrp_dbm=None if sheet is None else -95, hoja_origen=sheet)]

    app.dependency_overrides[get_repository] = lambda: Repository()
    with TestClient(app) as client:
        yield client, {"execution_id": str(execution_id), "hoja": "Datos 1"}, calls
    app.dependency_overrides.pop(get_repository, None)


def test_serialization_and_ecuador_time(geo_client):
    client, params, calls = geo_client
    response = client.get("/api/v1/geoespacial/mediciones", params=params | {"desde": "2026-05-05T08:00:00-05:00"})
    assert response.status_code == 200
    assert response.json()["mediciones"][0]["latitud"] == -0.2
    assert [str(key) for key in calls[0][0]] == [params["execution_id"]]
    assert calls[0][2].astimezone(timezone.utc).hour == 13


def test_csv_without_sheet_or_rsrp(geo_client):
    client, params, calls = geo_client
    response = client.get(f"/api/v1/geoespacial/ejecuciones/{params['execution_id']}/hojas")
    assert response.status_code == 200
    assert response.json() == ["Datos 1", None]
    response = client.get("/api/v1/geoespacial/mediciones", params={"execution_id": params["execution_id"], "tecnologia": 2})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert "rsrp_dbm" not in response.json()["mediciones"][0]
    assert calls[0][1] is None


@pytest.mark.parametrize("filters", [
    {"desde": "2026-05-05T08:00:00"},
    {"desde": "2026-05-06T00:00:00Z", "hasta": "2026-05-05T00:00:00Z"},
    {"bbox": "1,2,3"}, {"bbox": "nan,0,1,2"}, {"bbox": "10,0,5,2"},
    {"tecnologia": 4}, {"cell_id": 0},
])
def test_invalid_filters_rejected_before_query(geo_client, filters):
    client, params, calls = geo_client
    assert client.get("/api/v1/geoespacial/mediciones", params=params | filters).status_code == 422
    assert calls == []


def test_unknown_execution_or_sheet(geo_client):
    client, params, calls = geo_client
    for changes in ({"execution_id": str(uuid4())}, {"hoja": "Otra"}):
        assert client.get("/api/v1/geoespacial/mediciones", params=params | changes).status_code == 404
    assert calls == []


def test_empty_filtered_result(geo_client):
    client, params, _ = geo_client
    response = client.get("/api/v1/geoespacial/mediciones", params=params | {"cell_id": 99})
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_multiple_sessions_are_passed_to_repository(geo_client):
    client, params, calls = geo_client
    second = str(uuid4())
    # Unknown sessions are rejected before any measurements are fetched.
    response = client.get("/api/v1/geoespacial/mediciones", params=[("execution_id", params["execution_id"]), ("execution_id", second)])
    assert response.status_code == 404
    assert calls == []


def test_db_errors_do_not_expose_connection_details():
    class BrokenSession:
        def execute(self, query):
            raise OperationalError("secret connection string", {}, Exception("secret"))
    app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/geoespacial/ejecuciones")
        assert response.status_code == 503
        assert "secret" not in response.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_radio_base_estimates_are_serialized_for_each_selected_session():
    ids = [uuid4(), uuid4()]

    class Repository:
        def execution(self, key):
            return object() if key in ids else None

        def measurements(self, keys, sheet, start, end):
            return [SimpleNamespace(
                id_registro=uuid4(), execution_id=key,
                timestamp_medicion=datetime(2026, 5, 5, 13, 0, i, tzinfo=timezone.utc),
                latitud=-0.2 + i * 0.001, longitud=-78.5, cell_id=10, node_id=100,
                tecnologia=1, earfcn=1700, psc_pci=21, rssi=-80, accuracy=5,
                rsrp_dbm=None, hoja_origen=None,
            ) for key in keys for i in range(5)]

    app.dependency_overrides[get_repository] = lambda: Repository()
    try:
        with TestClient(app) as client:
            params = [('execution_id', str(key)) for key in ids]
            response = client.get('/api/v1/geoespacial/mediciones', params=params)
            assert response.status_code == 200
            data = response.json()
            assert len(data['radios_base']) == 2
            assert {p['execution_id'] for p in data['radios_base']} == {str(key) for key in ids}
            assert data['radios_base'][0]['psc_pci'] == [21]
            assert data['mediciones'][0]['earfcn'] == 1700
            assert data['resumen_radios_base']['parametros']['min_positions'] == 5
            filtered = client.get('/api/v1/geoespacial/mediciones', params=params + [('tecnologia', '2')])
            assert filtered.status_code == 200
            assert filtered.json()['radios_base'] == []
    finally:
        app.dependency_overrides.pop(get_repository, None)
