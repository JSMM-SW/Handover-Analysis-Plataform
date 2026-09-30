"""
Pruebas de integración de la API del Módulo 2 (Fase 3, tarea 3.5).

Recorren la pila completa —router, services, repository y base de datos— contra la sesión
sintética cargada por `docs/sql/03_datos_prueba.sql`.

Se omiten automáticamente si no hay conexión a Supabase, para que la suite siga siendo ejecutable
en un entorno sin credenciales.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.fixtures.dataset_sintetico import (
    SESION_ID,
    SESION_NOMBRE,
    TOTAL_HANDOVERS_ESPERADOS,
    TOTAL_MEDICIONES_ESPERADAS,
)

BASE = "/api/v1/visualizacion-temporal"
SESION_INEXISTENTE = "00000000-0000-4000-8000-000000000000"


@pytest.fixture(scope="module")
def cliente():
    from app.modules.visualizacion_temporal.repository import VisualizacionTemporalRepository
    from app.shared.db.database import SessionLocal

    try:
        db = SessionLocal()
        hay_datos = VisualizacionTemporalRepository(db).existe_sesion(SESION_ID)
        db.close()
    except Exception as exc:  # noqa: BLE001 - sin BD la suite debe seguir corriendo
        pytest.skip(f"Sin conexión a la base de datos: {exc}")

    if not hay_datos:
        pytest.skip("La sesión sintética no está cargada; ejecuta docs/sql/03_datos_prueba.sql")

    return TestClient(app)


@pytest.fixture(scope="module")
def sesion(cliente):
    """Deja la sesión sintética con sus handovers detectados."""
    cliente.post(f"{BASE}/sesiones/{SESION_ID}/detectar-handovers", json={})
    return SESION_ID


# ================================================================================================
# Camino feliz de los 8 endpoints
# ================================================================================================


def test_listar_sesiones_incluye_la_sesion_sintetica(cliente):
    respuesta = cliente.get(f"{BASE}/sesiones")

    assert respuesta.status_code == 200
    sesiones = {s["sesion_id"]: s for s in respuesta.json()}
    assert SESION_ID in sesiones
    assert sesiones[SESION_ID]["sesion_nombre"] == SESION_NOMBRE
    assert sesiones[SESION_ID]["n_mediciones"] == TOTAL_MEDICIONES_ESPERADAS
    assert sesiones[SESION_ID]["n_celdas"] == 8


def test_detectar_handovers_encuentra_los_esperados(cliente):
    respuesta = cliente.post(f"{BASE}/sesiones/{SESION_ID}/detectar-handovers", json={})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total_handovers"] == TOTAL_HANDOVERS_ESPERADOS
    assert cuerpo["por_tipo"]["inter_rat"] == 2
    assert cuerpo["total_ping_pong"] == 1


def test_la_deteccion_es_idempotente(cliente):
    """Reejecutarla no acumula duplicados."""
    primera = cliente.post(f"{BASE}/sesiones/{SESION_ID}/detectar-handovers", json={}).json()
    segunda = cliente.post(f"{BASE}/sesiones/{SESION_ID}/detectar-handovers", json={}).json()

    assert primera["total_handovers"] == segunda["total_handovers"]

    total = cliente.get(f"{BASE}/handovers", params={"sesion_id": SESION_ID}).json()["total"]
    assert total == TOTAL_HANDOVERS_ESPERADOS


def test_listar_handovers_devuelve_la_tabla_de_eventos(cliente, sesion):
    respuesta = cliente.get(f"{BASE}/handovers", params={"sesion_id": sesion})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == TOTAL_HANDOVERS_ESPERADOS

    evento = cuerpo["items"][0]
    for campo in ("celda_origen", "celda_destino", "timestamp_evento", "tipo_evento", "confianza"):
        assert campo in evento
    assert evento["celda_origen"]["clave"] != evento["celda_destino"]["clave"]


def test_la_paginacion_de_handovers_funciona(cliente, sesion):
    pagina = cliente.get(
        f"{BASE}/handovers", params={"sesion_id": sesion, "page": 2, "page_size": 3}
    ).json()

    assert pagina["total"] == TOTAL_HANDOVERS_ESPERADOS
    assert pagina["page"] == 2
    assert len(pagina["items"]) == 3


def test_series_devuelve_formato_columnar_alineado(cliente, sesion):
    respuesta = cliente.get(
        f"{BASE}/series",
        params={"sesion_id": sesion, "parametros": ["rsrp_dbm", "rssnr_db"]},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()

    assert set(cuerpo["series"]) == {"rsrp_dbm", "rssnr_db"}
    for serie in cuerpo["series"].values():
        assert len(serie) == len(cuerpo["t"]), "Los arrays deben quedar alineados con el eje t"


def test_series_corta_la_linea_en_el_hueco_de_captura(cliente, sesion):
    """El dataset tiene 30 s sin datos: la gráfica no debe unir los dos lados."""
    cuerpo = cliente.get(f"{BASE}/series", params={"sesion_id": sesion}).json()

    assert cuerpo["t"].count(None) == 1


def test_series_aplica_downsampling_y_lo_declara(cliente, sesion):
    cuerpo = cliente.get(
        f"{BASE}/series", params={"sesion_id": sesion, "max_puntos": 100}
    ).json()

    assert cuerpo["downsampled"] is True
    assert cuerpo["puntos_originales"] == TOTAL_MEDICIONES_ESPERADAS
    assert cuerpo["puntos_devueltos"] <= 100


def test_ningun_endpoint_de_series_supera_max_puntos(cliente, sesion):
    """Criterio de cierre de la fase."""
    for max_puntos in (10, 50, 250):
        cuerpo = cliente.get(
            f"{BASE}/series", params={"sesion_id": sesion, "max_puntos": max_puntos}
        ).json()

        assert cuerpo["puntos_devueltos"] <= max_puntos

        # `t` puede llevar además los nulos que cortan la línea en los huecos de captura.
        cortes = cuerpo["t"].count(None)
        for nombre, serie in cuerpo["series"].items():
            assert len(serie) == len(cuerpo["t"]), f"{nombre} no está alineada con el eje t"
            assert len(serie) - cortes <= max_puntos, f"{nombre} excede el máximo pedido"


def test_series_informa_de_los_parametros_sin_datos(cliente, sesion):
    """Decisión D-5: la interfaz debe poder decir 'sin datos válidos'."""
    cuerpo = cliente.get(
        f"{BASE}/series",
        params={"sesion_id": sesion, "parametros": ["rsrp_dbm", "rssi_dbm"]},
    ).json()

    cobertura = {c["parametro"]: c for c in cuerpo["cobertura"]}
    assert cobertura["rsrp_dbm"]["disponible"] is True
    assert cobertura["rssi_dbm"]["disponible"] is False
    assert cobertura["rssi_dbm"]["n_validos"] == 0


def test_series_celdas_devuelve_tramos_con_altura_estable(cliente, sesion):
    respuesta = cliente.get(f"{BASE}/series-celdas", params={"sesion_id": sesion})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["celdas_distintas"] == 8

    # La misma celda debe estar siempre a la misma altura.
    alturas: dict[str, float] = {}
    for tramo in cuerpo["tramos"]:
        clave = tramo["celda_clave"]
        if clave in alturas:
            assert alturas[clave] == tramo["valor_normalizado"]
        alturas[clave] = tramo["valor_normalizado"]
        assert 0.0 <= tramo["valor_normalizado"] <= 1.0


def test_series_celdas_admite_el_eje_por_pci(cliente, sesion):
    """Decisión D-2: se ofrecen los dos identificadores."""
    cuerpo = cliente.get(
        f"{BASE}/series-celdas", params={"sesion_id": sesion, "eje": "psc_pci"}
    ).json()

    assert cuerpo["eje"] == "psc_pci"
    assert all(tramo["etiqueta"] for tramo in cuerpo["tramos"])


def test_ventana_de_handover_devuelve_pre_evento_y_post(cliente, sesion):
    eventos = cliente.get(f"{BASE}/handovers", params={"sesion_id": sesion}).json()["items"]
    id_evento = eventos[0]["id_evento"]

    respuesta = cliente.get(
        f"{BASE}/handovers/{id_evento}/ventana",
        params={"segundos_antes": 5, "segundos_despues": 5},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()

    assert cuerpo["fase"].count("evento") == 1
    assert "pre" in cuerpo["fase"] and "post" in cuerpo["fase"]
    assert len(cuerpo["t"]) == len(cuerpo["t_relativo_s"]) == len(cuerpo["fase"])
    assert cuerpo["t_relativo_s"][0] < 0 < cuerpo["t_relativo_s"][-1]


def test_la_ventana_calcula_estadisticas_pre_post(cliente, sesion):
    eventos = cliente.get(f"{BASE}/handovers", params={"sesion_id": sesion}).json()["items"]
    cuerpo = cliente.get(f"{BASE}/handovers/{eventos[0]['id_evento']}/ventana").json()

    rsrp = cuerpo["estadisticas"]["rsrp_dbm"]
    assert rsrp["disponible"] is True
    assert rsrp["media_pre"] is not None and rsrp["media_post"] is not None
    assert rsrp["delta"] == pytest.approx(rsrp["media_post"] - rsrp["media_pre"], abs=0.02)


def test_un_parametro_sin_medidas_no_inventa_estadisticas(cliente, sesion):
    """`delta` debe ser null, nunca 0, cuando no hay con qué comparar."""
    eventos = cliente.get(f"{BASE}/handovers", params={"sesion_id": sesion}).json()["items"]
    cuerpo = cliente.get(f"{BASE}/handovers/{eventos[0]['id_evento']}/ventana").json()

    rssi = cuerpo["estadisticas"]["rssi_dbm"]
    assert rssi["disponible"] is False
    assert rssi["delta"] is None
    assert rssi["media_pre"] is None


def test_resumen_devuelve_los_totales_de_hu_007(cliente, sesion):
    respuesta = cliente.get(f"{BASE}/resumen", params={"sesion_id": sesion})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total_handovers"] == TOTAL_HANDOVERS_ESPERADOS
    assert cuerpo["radiobases_involucradas"] == 8
    assert cuerpo["sesiones_analizadas"] == 1
    assert cuerpo["tasa_ho_por_minuto"] > 0


def test_celdas_repetidas_devuelve_el_histograma(cliente, sesion):
    respuesta = cliente.get(
        f"{BASE}/celdas-repetidas", params={"sesion_id": sesion, "intervalo": "total", "top": 5}
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total_celdas"] == 8
    assert len(cuerpo["bins"]) == 1

    celdas = cuerpo["bins"][0]["celdas"]
    assert len(celdas) <= 5
    # La celda E se visita dos veces (ping-pong): debe encabezar el histograma.
    assert celdas[0]["n_visitas"] == 2


def test_celdas_repetidas_admite_intervalos(cliente, sesion):
    cuerpo = cliente.get(
        f"{BASE}/celdas-repetidas", params={"sesion_id": sesion, "intervalo": "5min"}
    ).json()

    assert cuerpo["intervalo"] == "5min"
    assert len(cuerpo["bins"]) >= 2
    assert all(b["inicio"] and b["fin"] for b in cuerpo["bins"])


# ================================================================================================
# Errores
# ================================================================================================


@pytest.mark.parametrize(
    "ruta", ["/handovers", "/series", "/series-celdas", "/resumen", "/celdas-repetidas"]
)
def test_sesion_inexistente_devuelve_404(cliente, ruta):
    respuesta = cliente.get(f"{BASE}{ruta}", params={"sesion_id": SESION_INEXISTENTE})

    assert respuesta.status_code == 404
    assert "no existe" in respuesta.json()["detail"].lower()


def test_detectar_sobre_sesion_inexistente_devuelve_404(cliente):
    respuesta = cliente.post(
        f"{BASE}/sesiones/{SESION_INEXISTENTE}/detectar-handovers", json={}
    )

    assert respuesta.status_code == 404


def test_handover_inexistente_devuelve_404(cliente):
    respuesta = cliente.get(f"{BASE}/handovers/{SESION_INEXISTENTE}/ventana")

    assert respuesta.status_code == 404


def test_rango_temporal_invertido_devuelve_422(cliente, sesion):
    respuesta = cliente.get(
        f"{BASE}/series",
        params={
            "sesion_id": sesion,
            "desde": "2026-07-01T14:00:00Z",
            "hasta": "2026-07-01T13:00:00Z",
        },
    )

    assert respuesta.status_code == 422


def test_rango_horario_invertido_devuelve_422(cliente, sesion):
    respuesta = cliente.get(
        f"{BASE}/series",
        params={"sesion_id": sesion, "hora_inicio": "18:00", "hora_fin": "09:00"},
    )

    assert respuesta.status_code == 422


def test_parametro_rf_desconocido_devuelve_422(cliente, sesion):
    respuesta = cliente.get(
        f"{BASE}/series", params={"sesion_id": sesion, "parametros": ["no_existe"]}
    )

    assert respuesta.status_code == 422


def test_tecnologia_desconocida_devuelve_422(cliente, sesion):
    respuesta = cliente.get(
        f"{BASE}/handovers", params={"sesion_id": sesion, "tecnologia": ["5G-NR"]}
    )

    assert respuesta.status_code == 422


def test_un_filtro_sin_resultados_devuelve_200_con_listas_vacias(cliente, sesion):
    """Una sesión válida sin datos en el rango no es un error."""
    parametros = {
        "sesion_id": sesion,
        "desde": "2027-01-01T00:00:00Z",
        "hasta": "2027-01-02T00:00:00Z",
    }

    series = cliente.get(f"{BASE}/series", params=parametros)
    handovers = cliente.get(f"{BASE}/handovers", params=parametros)

    assert series.status_code == 200
    assert series.json()["t"] == []
    assert handovers.status_code == 200
    assert handovers.json()["items"] == []


# ================================================================================================
# Consistencia entre endpoints — HU-C2-006 CA3
# ================================================================================================


def test_el_mismo_filtro_da_los_mismos_eventos_en_handovers_y_resumen(cliente, sesion):
    """Criterio de cierre: mismo filtro, mismos resultados en todos los endpoints."""
    parametros = {
        "sesion_id": sesion,
        "desde": "2026-07-01T13:00:00Z",
        "hasta": "2026-07-01T13:05:00Z",
    }

    handovers = cliente.get(f"{BASE}/handovers", params=parametros).json()
    resumen = cliente.get(f"{BASE}/resumen", params=parametros).json()

    assert handovers["total"] == resumen["total_handovers"]


def test_el_filtro_temporal_recorta_de_verdad(cliente, sesion):
    completo = cliente.get(f"{BASE}/resumen", params={"sesion_id": sesion}).json()
    recortado = cliente.get(
        f"{BASE}/resumen",
        params={
            "sesion_id": sesion,
            "desde": "2026-07-01T13:00:00Z",
            "hasta": "2026-07-01T13:03:00Z",
        },
    ).json()

    assert recortado["n_mediciones"] < completo["n_mediciones"]
    assert recortado["total_handovers"] <= completo["total_handovers"]


def test_el_filtro_por_tecnologia_se_aplica(cliente, sesion):
    solo_lte = cliente.get(
        f"{BASE}/resumen", params={"sesion_id": sesion, "tecnologia": ["LTE"]}
    ).json()
    completo = cliente.get(f"{BASE}/resumen", params={"sesion_id": sesion}).json()

    assert solo_lte["n_mediciones"] < completo["n_mediciones"]


def test_los_8_endpoints_estan_documentados_en_openapi(cliente):
    """Criterio de cierre: los 8 aparecen en /docs."""
    esquema = cliente.get("/openapi.json").json()
    rutas = [r for r in esquema["paths"] if "visualizacion-temporal" in r]

    assert len(rutas) == 8
    for ruta in rutas:
        for operacion in esquema["paths"][ruta].values():
            assert operacion.get("summary"), f"{ruta} sin summary"
            assert operacion.get("description"), f"{ruta} sin description"
            assert operacion["tags"] == ["Visualización Temporal"]
