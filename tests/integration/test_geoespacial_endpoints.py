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
            return ["Datos 1"]

        def measurements(self, key, sheet, start, end):
            calls.append((key, sheet, start, end))
            return [SimpleNamespace(id_registro=uuid4(), timestamp_medicion=datetime(2026, 5, 5, 13, tzinfo=timezone.utc),
                                    latitud=-0.2, longitud=-78.5, cell_id=10, tecnologia=1, rsrp_dbm=-95, hoja_origen=sheet)]

    app.dependency_overrides[get_repository] = lambda: Repository()
    with TestClient(app) as client:
        yield client, {"execution_id": str(execution_id), "hoja": "Datos 1"}, calls
    app.dependency_overrides.pop(get_repository, None)


def test_serialization_and_ecuador_time(geo_client):
    client, params, calls = geo_client
    response = client.get("/api/v1/geoespacial/mediciones", params=params | {"desde": "2026-05-05T08:00:00-05:00"})
    assert response.status_code == 200
    assert response.json()["mediciones"][0]["latitud"] == -0.2
    assert calls[0][2].astimezone(timezone.utc).hour == 13


@pytest.mark.parametrize("filters", [
    {"desde": "2026-05-05T08:00:00"},
    {"desde": "2026-05-06T00:00:00Z", "hasta": "2026-05-05T00:00:00Z"},
    {"bbox": "1,2,3"}, {"bbox": "nan,0,1,2"}, {"bbox": "10,0,5,2"},
    {"tecnologia": 3}, {"cell_id": 0},
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


def test_db_errors_do_not_expose_connection_details():
    class BrokenSession:
        def scalars(self, query):
            raise OperationalError("secret connection string", {}, Exception("secret"))
    app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/geoespacial/ejecuciones")
        assert response.status_code == 503
        assert "secret" not in response.text
    finally:
        app.dependency_overrides.pop(get_db, None)
