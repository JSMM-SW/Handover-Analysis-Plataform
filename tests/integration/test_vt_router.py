"""
Pruebas de integración de la API del Módulo 2 (Fase 3, tarea 3.5).

Recorren la pila completa —router, services, repository y base de datos— contra las sesiones
**reales** que el Módulo 1 ha cargado en `handover_record`. No hay datos sintéticos en la base:
como las cifras de cada recorrido real no se conocen de antemano, las pruebas comprueban
propiedades (alineación, coherencia entre endpoints, idempotencia) en lugar de totales exactos.
La verdad de referencia del detector se prueba en memoria en `tests/unit/`.

Todo corre dentro de una transacción que se revierte al terminar el módulo: la detección que
lanzan estas pruebas borra y reinserta eventos, pero nunca llega a confirmarse, así que los
eventos reales de `eventos_handover` quedan intactos.

Se omiten automáticamente si no hay conexión a Supabase o no hay sesiones cargadas, para que la
suite siga siendo ejecutable en un entorno sin credenciales.
"""

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.shared.db.database import get_db

BASE = "/api/v1/visualizacion-temporal"
SESION_INEXISTENTE = "00000000-0000-4000-8000-000000000000"

#: Mínimo de mediciones para que una sesión sirva de ejemplo (downsampling, ventanas...).
MIN_MEDICIONES = 300

#: Zona del usuario en las pruebas de franja horaria y disponibilidad. Ecuador no tiene horario
#: de verano, así que el desfase con UTC es siempre el mismo (−5 h).
ZONA = "America/Guayaquil"


@pytest.fixture(scope="module")
def conexion():
    """Conexión con una transacción exterior que se revierte al final del módulo."""
    from app.shared.db.database import engine

    try:
        conexion = engine.connect()
    except Exception as exc:  # noqa: BLE001 - sin BD la suite debe seguir corriendo
        pytest.skip(f"Sin conexión a la base de datos: {exc}")

    transaccion = conexion.begin()
    yield conexion
    transaccion.rollback()
    conexion.close()


@pytest.fixture(scope="module")
def cliente(conexion):
    # Cada `commit()` del repositorio libera un SAVEPOINT; la transacción exterior sigue abierta.
    db = Session(bind=conexion, join_transaction_mode="create_savepoint")

    def get_db_de_prueba():
        yield db

    app.dependency_overrides[get_db] = get_db_de_prueba
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


@pytest.fixture(scope="module")
def sesiones(cliente):
    respuesta = cliente.get(f"{BASE}/sesiones")
    assert respuesta.status_code == 200

    sesiones = respuesta.json()
    if not sesiones:
        pytest.skip("No hay sesiones cargadas por el ETL en handover_record")
    return sesiones


def _duracion_s(sesion: dict) -> float:
    inicio = datetime.fromisoformat(sesion["inicio"])
    fin = datetime.fromisoformat(sesion["fin"])
    return (fin - inicio).total_seconds()


@pytest.fixture(scope="module")
def sesion_lte(sesiones):
    """La sesión LTE más pequeña que sigue siendo representativa (>10 min y >300 mediciones)."""
    candidatas = [
        s
        for s in sesiones
        if "LTE" in s["tecnologias"]
        and s["n_mediciones"] >= MIN_MEDICIONES
        and _duracion_s(s) > 600
    ]
    if not candidatas:
        pytest.skip("No hay ninguna sesión LTE con suficientes mediciones")
    return min(candidatas, key=lambda s: s["n_mediciones"])


@pytest.fixture(scope="module")
def sesion(cliente, sesion_lte):
    """Deja la sesión con sus handovers detectados (dentro de la transacción de prueba)."""
    respuesta = cliente.post(
        f"{BASE}/sesiones/{sesion_lte['sesion_id']}/detectar-handovers", json={}
    )
    assert respuesta.status_code == 200
    return sesion_lte["sesion_id"]


@pytest.fixture(scope="module")
def eventos(cliente, sesion):
    items = cliente.get(f"{BASE}/handovers", params={"sesion_id": sesion}).json()["items"]
    if not items:
        pytest.skip("La sesión elegida no tiene handovers con los parámetros por defecto")
    return items


# ================================================================================================
# Camino feliz de los 9 endpoints
# ================================================================================================


def test_listar_sesiones_devuelve_sesiones_con_nombre_y_totales(sesiones):
    for s in sesiones:
        assert s["sesion_nombre"]
        assert s["n_mediciones"] > 0
        assert s["n_celdas"] > 0
        assert s["inicio"] <= s["fin"]
        assert "origen" not in s


def test_detectar_handovers_devuelve_el_resumen(cliente, sesion_lte):
    respuesta = cliente.post(
        f"{BASE}/sesiones/{sesion_lte['sesion_id']}/detectar-handovers", json={}
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total_handovers"] >= 0
    assert sum(cuerpo["por_tipo"].values()) == cuerpo["total_handovers"]


def test_la_deteccion_es_idempotente(cliente, sesion):
    """Reejecutarla no acumula duplicados."""
    primera = cliente.post(f"{BASE}/sesiones/{sesion}/detectar-handovers", json={}).json()
    segunda = cliente.post(f"{BASE}/sesiones/{sesion}/detectar-handovers", json={}).json()

    assert primera["total_handovers"] == segunda["total_handovers"]

    total = cliente.get(f"{BASE}/handovers", params={"sesion_id": sesion}).json()["total"]
    assert total == segunda["total_handovers"]


def test_listar_handovers_devuelve_la_tabla_de_eventos(eventos):
    evento = eventos[0]
    for campo in ("celda_origen", "celda_destino", "timestamp_evento", "tipo_evento", "confianza"):
        assert campo in evento
    assert evento["celda_origen"]["clave"] != evento["celda_destino"]["clave"]


def test_la_paginacion_de_handovers_funciona(cliente, sesion):
    total = cliente.get(f"{BASE}/handovers", params={"sesion_id": sesion}).json()["total"]
    pagina = cliente.get(
        f"{BASE}/handovers", params={"sesion_id": sesion, "page": 2, "page_size": 3}
    ).json()

    assert pagina["total"] == total
    assert pagina["page"] == 2
    assert len(pagina["items"]) == min(3, max(0, total - 3))


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


def test_los_cortes_de_linea_son_nulos_en_todas_las_series(cliente, sesion):
    """Un hueco de captura corta la línea a la vez en el eje t y en todas las series."""
    cuerpo = cliente.get(f"{BASE}/series", params={"sesion_id": sesion}).json()

    for indice, instante in enumerate(cuerpo["t"]):
        if instante is None:
            assert all(serie[indice] is None for serie in cuerpo["series"].values())


def test_series_aplica_downsampling_y_lo_declara(cliente, sesion_lte, sesion):
    cuerpo = cliente.get(
        f"{BASE}/series", params={"sesion_id": sesion, "max_puntos": 100}
    ).json()

    assert cuerpo["downsampled"] is True
    assert cuerpo["puntos_originales"] == sesion_lte["n_mediciones"]
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
    """Decisión D-5: la interfaz debe poder decir 'sin datos válidos'.

    RSCP no tiene columna de origen en el ETL actual, así que nunca tiene medidas.
    """
    cuerpo = cliente.get(
        f"{BASE}/series",
        params={"sesion_id": sesion, "parametros": ["rsrp_dbm", "rscp_dbm"]},
    ).json()

    cobertura = {c["parametro"]: c for c in cuerpo["cobertura"]}
    assert cobertura["rsrp_dbm"]["disponible"] is True
    assert cobertura["rscp_dbm"]["disponible"] is False
    assert cobertura["rscp_dbm"]["n_validos"] == 0


def test_series_celdas_devuelve_tramos_con_altura_estable(cliente, sesion):
    respuesta = cliente.get(f"{BASE}/series-celdas", params={"sesion_id": sesion})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["celdas_distintas"] > 0

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


def test_ventana_de_handover_devuelve_pre_evento_y_post(cliente, eventos):
    respuesta = cliente.get(
        f"{BASE}/handovers/{eventos[0]['id_evento']}/ventana",
        params={"segundos_antes": 5, "segundos_despues": 5},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()

    assert "evento" in cuerpo["fase"]
    assert len(cuerpo["t"]) == len(cuerpo["t_relativo_s"]) == len(cuerpo["fase"])
    for relativo, fase in zip(cuerpo["t_relativo_s"], cuerpo["fase"]):
        assert -5 <= relativo <= 5
        assert fase == ("pre" if relativo < 0 else "evento" if relativo == 0 else "post")


def test_la_ventana_calcula_estadisticas_pre_post(cliente, eventos):
    cuerpo = cliente.get(f"{BASE}/handovers/{eventos[0]['id_evento']}/ventana").json()

    rsrp = cuerpo["estadisticas"]["rsrp_dbm"]
    if rsrp["media_pre"] is None or rsrp["media_post"] is None:
        pytest.skip("El primer evento no tiene RSRP a ambos lados")
    assert rsrp["delta"] == pytest.approx(rsrp["media_post"] - rsrp["media_pre"], abs=0.02)


def test_un_parametro_sin_medidas_no_inventa_estadisticas(cliente, eventos):
    """`delta` debe ser null, nunca 0, cuando no hay con qué comparar."""
    cuerpo = cliente.get(f"{BASE}/handovers/{eventos[0]['id_evento']}/ventana").json()

    rscp = cuerpo["estadisticas"]["rscp_dbm"]
    assert rscp["disponible"] is False
    assert rscp["delta"] is None
    assert rscp["media_pre"] is None


def test_resumen_devuelve_los_totales_de_hu_007(cliente, sesion_lte, sesion):
    respuesta = cliente.get(f"{BASE}/resumen", params={"sesion_id": sesion})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    total = cliente.get(f"{BASE}/handovers", params={"sesion_id": sesion}).json()["total"]

    assert cuerpo["total_handovers"] == total
    assert cuerpo["n_mediciones"] == sesion_lte["n_mediciones"]
    assert cuerpo["radiobases_involucradas"] > 0
    assert cuerpo["sesiones_analizadas"] == 1


def test_celdas_repetidas_devuelve_el_histograma(cliente, sesion):
    respuesta = cliente.get(
        f"{BASE}/celdas-repetidas", params={"sesion_id": sesion, "intervalo": "total", "top": 5}
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total_celdas"] > 0
    assert len(cuerpo["bins"]) == 1

    celdas = cuerpo["bins"][0]["celdas"]
    assert 0 < len(celdas) <= 5
    # Las más visitadas primero.
    visitas = [c["n_visitas"] for c in celdas]
    assert visitas == sorted(visitas, reverse=True)


def test_celdas_repetidas_admite_intervalos_en_minutos(cliente, sesion_lte, sesion):
    """El deslizador manda minutos: cada intervalo dura eso y se cuenta desde el inicio de la sesión."""
    cuerpo = cliente.get(
        f"{BASE}/celdas-repetidas", params={"sesion_id": sesion, "minutos": 3}
    ).json()

    assert cuerpo["minutos"] == 3
    assert 1 <= cuerpo["minutos_max"] <= math.ceil(_duracion_s(sesion_lte) / 60)
    assert len(cuerpo["bins"]) >= 2
    for intervalo in cuerpo["bins"]:
        assert intervalo["sesion_id"] == sesion
        duracion = datetime.fromisoformat(intervalo["fin"]) - datetime.fromisoformat(intervalo["inicio"])
        assert duracion == timedelta(minutes=3)


def test_celdas_repetidas_por_pci_psc(cliente, sesion):
    """Por PCI/PSC hay a lo sumo tantas barras como celdas: las que comparten PCI suman juntas."""
    por_celda = cliente.get(f"{BASE}/celdas-repetidas", params={"sesion_id": sesion}).json()
    por_pci = cliente.get(
        f"{BASE}/celdas-repetidas", params={"sesion_id": sesion, "eje": "psc_pci", "top": 200}
    ).json()

    assert por_pci["eje"] == "psc_pci"
    assert 0 < por_pci["total_celdas"] <= por_celda["total_celdas"]
    rotulos = [c["etiqueta"] for c in por_pci["bins"][0]["celdas"]]
    assert len(rotulos) == len(set(rotulos))
    assert all(r.startswith(("PCI ", "PSC ", "GSM CID ", "Sin ")) for r in rotulos)
    assert not any("LTE CID" in r for r in rotulos)


def test_celdas_repetidas_admite_intervalos(cliente, sesion):
    """La sesión dura más de 10 minutos, así que en tramos de 5 hay al menos dos."""
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
    "ruta",
    ["/handovers", "/series", "/series-celdas", "/resumen", "/celdas-repetidas", "/disponibilidad"],
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


def test_una_tecnologia_que_no_esta_en_los_datos_no_deja_pasar_nada(cliente, sesion):
    """Las tecnologías no están fijadas en el código: una que no aparece filtra todo, sin error."""
    respuesta = cliente.get(
        f"{BASE}/handovers", params={"sesion_id": sesion, "tecnologia": ["5G-NR"]}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["total"] == 0


def test_una_tecnologia_mal_formada_devuelve_422(cliente, sesion):
    respuesta = cliente.get(
        f"{BASE}/handovers", params={"sesion_id": sesion, "tecnologia": ["LTE; DROP"]}
    )

    assert respuesta.status_code == 422


def test_una_zona_horaria_desconocida_devuelve_422(cliente, sesion):
    for ruta in ("/handovers", "/disponibilidad"):
        respuesta = cliente.get(
            f"{BASE}{ruta}", params={"sesion_id": sesion, "zona_horaria": "Marte/Olimpo"}
        )
        assert respuesta.status_code == 422, ruta


def test_un_filtro_sin_resultados_devuelve_200_con_listas_vacias(cliente, sesion):
    """Una sesión válida sin datos en el rango no es un error."""
    parametros = {
        "sesion_id": sesion,
        "desde": "2099-01-01T00:00:00Z",
        "hasta": "2099-01-02T00:00:00Z",
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


def _primeros_minutos(sesion: dict, minutos: int) -> dict:
    inicio = datetime.fromisoformat(sesion["inicio"])
    return {
        "sesion_id": sesion["sesion_id"],
        "desde": inicio.isoformat(),
        "hasta": (inicio + timedelta(minutes=minutos)).isoformat(),
    }


def test_el_mismo_filtro_da_los_mismos_eventos_en_handovers_y_resumen(cliente, sesion_lte, sesion):
    """Criterio de cierre: mismo filtro, mismos resultados en todos los endpoints."""
    parametros = _primeros_minutos(sesion_lte, 5)

    handovers = cliente.get(f"{BASE}/handovers", params=parametros).json()
    resumen = cliente.get(f"{BASE}/resumen", params=parametros).json()

    assert handovers["total"] == resumen["total_handovers"]


def test_el_filtro_temporal_recorta_de_verdad(cliente, sesion_lte, sesion):
    completo = cliente.get(f"{BASE}/resumen", params={"sesion_id": sesion}).json()
    recortado = cliente.get(f"{BASE}/resumen", params=_primeros_minutos(sesion_lte, 3)).json()

    assert recortado["n_mediciones"] < completo["n_mediciones"]
    assert recortado["total_handovers"] <= completo["total_handovers"]


def test_la_franja_horaria_se_interpreta_en_la_hora_local_del_usuario(cliente, sesion_lte, sesion):
    """Regresión: la franja se comparaba en UTC y la hora local de Ecuador no encontraba nada.

    Para una sesión de un solo día, la franja local de sus primeros minutos debe dar exactamente
    lo mismo que el rango de instantes equivalente.
    """
    inicio = datetime.fromisoformat(sesion_lte["inicio"])
    local = inicio.astimezone(ZoneInfo(ZONA))
    fin_local = local + timedelta(minutes=5)
    if fin_local.date() != local.date():
        pytest.skip("Los primeros minutos de la sesión cruzan la medianoche local")

    por_franja = cliente.get(
        f"{BASE}/resumen",
        params={
            "sesion_id": sesion,
            "hora_inicio": local.strftime("%H:%M:%S"),
            "hora_fin": fin_local.strftime("%H:%M:%S"),
            "zona_horaria": ZONA,
        },
    ).json()
    por_instantes = cliente.get(f"{BASE}/resumen", params=_primeros_minutos(sesion_lte, 5)).json()

    assert por_franja["n_mediciones"] > 0
    assert por_franja["n_mediciones"] == por_instantes["n_mediciones"]
    assert por_franja["total_handovers"] == por_instantes["total_handovers"]


def test_la_disponibilidad_cuadra_con_la_sesion(cliente, sesion_lte, sesion):
    """Días, franjas, handovers y tecnologías salen de la base y cuadran con los demás endpoints."""
    respuesta = cliente.get(
        f"{BASE}/disponibilidad", params={"sesion_id": sesion, "zona_horaria": ZONA}
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["zona_horaria"] == ZONA
    assert sum(d["n_mediciones"] for d in cuerpo["dias"]) == sesion_lte["n_mediciones"]

    total = cliente.get(f"{BASE}/handovers", params={"sesion_id": sesion}).json()["total"]
    assert sum(d["n_handovers"] for d in cuerpo["dias"]) == total
    assert cuerpo["tecnologias"] == sorted(sesion_lte["tecnologias"])

    # El primer día y su primera franja empiezan donde empieza la sesión, en hora local.
    inicio_local = datetime.fromisoformat(sesion_lte["inicio"]).astimezone(ZoneInfo(ZONA))
    primer_dia = cuerpo["dias"][0]
    assert primer_dia["fecha"] == inicio_local.date().isoformat()
    assert primer_dia["franjas"][0]["inicio"] == inicio_local.strftime("%H:%M:00")


def test_el_filtro_por_tecnologia_se_aplica(cliente, sesiones):
    """Necesita una sesión con más de una tecnología: filtrar por una deja fuera las demás."""
    mixtas = [s for s in sesiones if "LTE" in s["tecnologias"] and len(s["tecnologias"]) > 1]
    if not mixtas:
        pytest.skip("No hay ninguna sesión con varias tecnologías")
    sesion_mixta = min(mixtas, key=lambda s: s["n_mediciones"])["sesion_id"]

    solo_lte = cliente.get(
        f"{BASE}/resumen", params={"sesion_id": sesion_mixta, "tecnologia": ["LTE"]}
    ).json()
    completo = cliente.get(f"{BASE}/resumen", params={"sesion_id": sesion_mixta}).json()

    assert 0 < solo_lte["n_mediciones"] < completo["n_mediciones"]


def test_los_9_endpoints_estan_documentados_en_openapi(cliente):
    """Criterio de cierre: los 9 aparecen en /docs."""
    esquema = cliente.get("/openapi.json").json()
    rutas = [r for r in esquema["paths"] if "visualizacion-temporal" in r]

    assert len(rutas) == 9
    for ruta in rutas:
        for operacion in esquema["paths"][ruta].values():
            assert operacion.get("summary"), f"{ruta} sin summary"
            assert operacion.get("description"), f"{ruta} sin description"
            assert operacion["tags"] == ["Visualización Temporal"]
