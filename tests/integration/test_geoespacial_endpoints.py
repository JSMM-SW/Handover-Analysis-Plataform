from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app
from app.modules.visualizacion_geoespacial.router import get_repository
from app.modules.visualizacion_temporal.detector import Medicion, detectar_handovers
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

        def handovers(self, keys):
            return []

        def available_days(self, keys):
            return [{"fecha": "2026-05-05", "n_mediciones": 1}]

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


def test_available_dates_and_daily_hour_window(geo_client):
    client, params, _ = geo_client
    response = client.get('/api/v1/geoespacial/disponibilidad', params={'execution_id': params['execution_id']})
    assert response.status_code == 200
    assert response.json() == [{"fecha": "2026-05-05", "n_mediciones": 1}]
    for start, expected in [('08:00:00', 1), ('09:00:00', 0)]:
        response = client.get('/api/v1/geoespacial/mediciones', params=params | {'hora_inicio': start, 'hora_fin': '09:59:59'})
        assert response.status_code == 200
        assert response.json()['total'] == expected


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
    {"hora_inicio": "09:00", "hora_fin": "08:00"},
    {"vista_bbox": "bad"}, {"zoom": 23},
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
        def rollback(self):
            pass
    app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/geoespacial/ejecuciones")
        assert response.status_code == 503
        assert "secret" not in response.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_database_statement_timeout_is_reported_distinctly(caplog):
    class CanceledQuery(Exception):
        sqlstate = '57014'
    class Session:
        def execute(self, query):
            raise OperationalError('private query', {}, CanceledQuery('private connection'))
        def rollback(self):
            pass
    app.dependency_overrides[get_db] = lambda: Session()
    try:
        with TestClient(app) as client:
            response = client.get('/api/v1/geoespacial/ejecuciones')
        assert response.status_code == 504
        assert 'tiempo de espera' in response.json()['detail']
        assert '57014' in caplog.text
        assert 'private' not in response.text
        assert 'private' not in caplog.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_radio_base_estimates_are_serialized_for_each_selected_session():
    ids = [uuid4(), uuid4()]

    class Repository:
        def execution(self, key):
            return object() if key in ids else None

        def handovers(self, keys):
            return []

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


def test_handover_without_gps_is_counted_in_api_but_not_mapped():
    session_id = uuid4()
    rows = [SimpleNamespace(id_registro=uuid4(), execution_id=session_id,
                            timestamp_medicion=datetime(2026, 5, 5, 13, 0, index, tzinfo=timezone.utc),
                            cell_id=10 if index < 2 else 20, node_id=100, tecnologia=1,
                            latitud=-0.2 if index < 2 else None, longitud=-78.5 if index < 2 else None,
                            hoja_origen=None) for index in range(4)]

    class Repository:
        def execution(self, key):
            return object() if key == session_id else None

        def measurements(self, keys, sheet, start, end):
            return rows

        def handovers(self, keys):
            return detectar_handovers([Medicion(id_medicion=str(row.id_registro), sesion_id=str(session_id),
                                               timestamp_medicion=row.timestamp_medicion,
                                               cid=row.cell_id, node_id=row.node_id, tech='LTE') for row in rows])

    app.dependency_overrides[get_repository] = lambda: Repository()
    try:
        with TestClient(app) as client:
            response = client.get('/api/v1/geoespacial/mediciones', params={'execution_id': str(session_id)})
        assert response.status_code == 200
        data = response.json()
        assert data['total_handovers'] == data['handovers_sin_ubicacion'] == 1
        assert data['handovers_con_ubicacion'] == 0
        assert data['handovers'] == []
    finally:
        app.dependency_overrides.pop(get_repository, None)


def test_original_measurement_and_handover_details_are_loaded_by_id():
    session_id = uuid4()
    rows = [SimpleNamespace(id_registro=uuid4(), execution_id=session_id,
                            timestamp_medicion=datetime(2026, 5, 5, 13, 0, i, tzinfo=timezone.utc),
                            cell_id=10 if i < 2 else 20, node_id=100, tecnologia=1,
                            latitud=-0.2, longitud=-78.5, hoja_origen=None, rssi=-75) for i in range(4)]

    class Repository:
        def measurement(self, record_id):
            return next((row for row in rows if row.id_registro == record_id), None)

        def execution(self, execution_id):
            assert execution_id == session_id
            return SimpleNamespace(execution_id=session_id)

        def handovers(self, keys):
            assert keys == [session_id]
            return detectar_handovers([Medicion(id_medicion=str(row.id_registro), sesion_id=str(session_id),
                                               timestamp_medicion=row.timestamp_medicion,
                                               cid=row.cell_id, node_id=row.node_id, tech='LTE') for row in rows])

    app.dependency_overrides[get_repository] = lambda: Repository()
    try:
        with TestClient(app) as client:
            measurement = client.get(f'/api/v1/geoespacial/mediciones/{rows[2].id_registro}')
            assert measurement.status_code == 200
            assert measurement.json()['rssi'] == -75
            event = client.get(f'/api/v1/geoespacial/handovers/{rows[2].id_registro}')
            assert event.status_code == 200
            assert event.json()['registro_anterior_id'] == str(rows[1].id_registro)
            assert event.json()['celda_origen'] == 10
            assert client.get(f'/api/v1/geoespacial/handovers/{rows[0].id_registro}').status_code == 404
            assert client.get(f'/api/v1/geoespacial/mediciones/{uuid4()}').status_code == 404
    finally:
        app.dependency_overrides.pop(get_repository, None)


def test_large_api_preserves_all_signal_samples_and_reuses_analysis_on_zoom():
    session_id = uuid4()
    start = datetime(2026, 5, 5, 13, tzinfo=timezone.utc)
    rows = [SimpleNamespace(id_registro=uuid4(), execution_id=session_id,
                            timestamp_medicion=start + timedelta(seconds=i),
                            latitud=-0.2 + i * 0.000001, longitud=-78.5 + i * 0.000001,
                            cell_id=10, node_id=None, tecnologia=1, hoja_origen=None,
                            rssi=-100 if i % 2 else -80) for i in range(60001)]
    calls = []

    class Repository:
        def execution(self, key):
            return object() if key == session_id else None

        def measurements(self, *args):
            calls.append(1)
            return rows

        def handovers(self, keys):
            return []

    app.dependency_overrides[get_repository] = lambda: Repository()
    try:
        with TestClient(app) as client:
            params = {'execution_id': str(session_id)}
            response = client.get('/api/v1/geoespacial/mediciones', params=params)
            assert response.status_code == 200
            full = response.json()
            assert full['total'] == 60001
            assert full['mapa_resumido']
            assert len(full['mediciones']) <= 6000
            assert len(full['senales']) == 60001
            assert {sample[6] for sample in full['senales']} == {str(row.id_registro) for row in rows}
            assert full['senales'][0][2] == rows[0].rssi
            assert full['senales'][0][7] == rows[0].timestamp_medicion.isoformat().replace('+00:00', 'Z')
            response = client.get('/api/v1/geoespacial/mediciones', params=params | {
                'zoom': 17, 'vista_bbox': '-78.5,-0.2,-78.49,-0.19'})
            assert response.status_code == 200
            detail = response.json()
            assert detail['total'] == full['total']
            assert detail['promedios'] == full['promedios']
            assert detail['limites'] == full['limites']
            assert calls == [1]
    finally:
        app.dependency_overrides.pop(get_repository, None)
