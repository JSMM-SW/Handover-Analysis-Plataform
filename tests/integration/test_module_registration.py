from app.main import app


def test_both_visualization_modules_are_registered_in_the_shared_api():
    paths = app.openapi()["paths"]
    assert "/api/v1/geoespacial/ejecuciones" in paths
    assert "/api/v1/geoespacial/mediciones" in paths
    assert "/api/v1/visualizacion-temporal/sesiones" in paths
