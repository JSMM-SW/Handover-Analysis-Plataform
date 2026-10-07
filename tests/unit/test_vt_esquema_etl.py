"""
Pruebas de la adaptación del repositorio al esquema del ETL (BLQ-21).

El repositorio lee `handover_record` directamente y construye la consulta según las columnas que
existan en cada momento. Estas pruebas fijan el mapeo con los esquemas que el Módulo 1 ha tenido
y comprueban que la caché se renueva sola cuando el esquema cambia. No necesitan base de datos.
"""

import pytest
from sqlalchemy.exc import ProgrammingError

from app.modules.visualizacion_temporal import repository
from app.modules.visualizacion_temporal.repository import (
    VisualizacionTemporalRepository,
    construir_sql_mediciones,
    invalidar_cache_esquema,
)

BASE = {"id_registro", "execution_id", "timestamp_medicion"}

#: Esquema de `develop` (migraciones 001-004): solo columnas heredadas.
ESQUEMA_POBRE = BASE | {
    "cell_id", "tac", "earfcn", "tecnologia", "latitud", "longitud", "rsrp_dbm",
    "archivo_origen", "hoja_origen", "node_id", "psc_pci", "rssi", "rsrq", "rssnr",
}

#: Esquema con la migración 005 del ETL v2 aplicada (el que hoy tiene Supabase).
ESQUEMA_COMPLETO = ESQUEMA_POBRE | {
    "rscp_dbm", "rssi_dbm", "cid", "lac_tac_raw", "report_index", "net_type", "tech",
    "data_state", "call_state",
}


@pytest.fixture(autouse=True)
def _cache_limpia():
    invalidar_cache_esquema()
    yield
    invalidar_cache_esquema()


# ------------------------------------------------------------------------------------------------
# Mapeo de columnas
# ------------------------------------------------------------------------------------------------


def test_esquema_pobre_usa_las_columnas_heredadas():
    sql = construir_sql_mediciones(ESQUEMA_POBRE)

    assert 'h."cell_id"::bigint AS cid' in sql
    assert 'h."tac"::integer AS lac_tac' in sql
    assert 'h."earfcn"::integer AS arfcn' in sql
    assert 'h."rsrq"::smallint AS rsrq_db' in sql
    assert "CASE h.\"tecnologia\" WHEN 1 THEN 'LTE'" in sql
    # Lo que aún no existe llega como NULL del tipo correcto, sin romper la consulta.
    assert "NULL::integer AS report_index" in sql
    assert 'h."cid"' not in sql
    assert 'h."tech"' not in sql


def test_esquema_completo_prefiere_la_columna_nueva_y_cae_en_la_heredada():
    sql = construir_sql_mediciones(ESQUEMA_COMPLETO)

    assert 'COALESCE(h."cid", h."cell_id")::bigint AS cid' in sql
    assert 'COALESCE(h."lac_tac_raw", h."tac")::integer AS lac_tac' in sql
    assert "COALESCE(h.\"tech\", CASE h.\"tecnologia\"" in sql
    assert 'h."report_index"::integer AS report_index' in sql
    assert "NULL::smallint AS rscp_dbm" in sql
    assert 'h."rssi"::smallint AS rssi_dbm' in sql


def test_la_etiqueta_de_sesion_sale_de_etl_execution_si_no_esta_en_handover_record():
    sql = construir_sql_mediciones(ESQUEMA_POBRE, {"execution_id", "sesion_label"})

    assert 'LEFT JOIN etl_execution x ON x."execution_id" = h."execution_id"' in sql
    assert 'x."sesion_label"::text' in sql


def test_sin_etiqueta_de_sesion_no_hay_join():
    sql = construir_sql_mediciones(ESQUEMA_POBRE, {"execution_id"})

    assert "etl_execution" not in sql
    assert "NULL::text ~ '^[0-9]+$'" in sql


def test_la_consulta_proyecta_el_contrato_en_orden_mas_la_identidad_de_celda():
    sql = construir_sql_mediciones(ESQUEMA_COMPLETO)

    columnas = repository._COLUMNAS_MEDICION
    assert sql.startswith("SELECT " + ", ".join(f"r.{c}" for c in columnas))
    assert "AS celda_clave\n" in sql
    # La única fuente es handover_record: no hay datos sintéticos que unir.
    assert "UNION ALL" not in sql
    assert "vt_medicion_prueba" not in sql


@pytest.mark.parametrize(
    "columnas", [set(), BASE - {"timestamp_medicion"}], ids=["sin_tabla", "sin_columna_minima"]
)
def test_sin_handover_record_utilizable_falla_con_un_mensaje_claro(columnas):
    with pytest.raises(RuntimeError, match="No hay fuente de mediciones"):
        construir_sql_mediciones(columnas)


# ------------------------------------------------------------------------------------------------
# Caché del esquema
# ------------------------------------------------------------------------------------------------


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def all(self):
        return self._filas

    def first(self):
        return self._filas[0] if self._filas else None


class SesionFalsa:
    """Sesión mínima: responde a `information_schema` y registra el resto de consultas."""

    def __init__(self, columnas_etl, fallos=0):
        self.columnas_etl = set(columnas_etl)
        self.fallos_pendientes = fallos
        self.lecturas_esquema = 0
        self.consultas = []
        self.rollbacks = 0

    def execute(self, sql, parametros=None):
        texto = str(sql)
        if "information_schema" in texto:
            self.lecturas_esquema += 1
            return _Resultado([("handover_record", c) for c in self.columnas_etl])

        self.consultas.append(texto)
        if self.fallos_pendientes:
            self.fallos_pendientes -= 1
            raise ProgrammingError(texto, parametros, Exception("column does not exist"))
        return _Resultado([(1,)])

    def rollback(self):
        self.rollbacks += 1


def test_el_esquema_se_lee_una_vez_y_se_reutiliza():
    sesion = SesionFalsa(ESQUEMA_COMPLETO)
    repo = VisualizacionTemporalRepository(sesion)

    repo.existe_sesion("s1")
    repo.existe_sesion("s2")

    assert sesion.lecturas_esquema == 1
    assert 'h."report_index"' in sesion.consultas[-1]


def test_si_una_columna_desaparece_se_relee_el_esquema_y_se_reintenta():
    sesion = SesionFalsa(ESQUEMA_COMPLETO)
    repo = VisualizacionTemporalRepository(sesion)
    repo.existe_sesion("s1")

    # El Módulo 1 quita `report_index` y la primera consulta con la caché vieja falla.
    sesion.columnas_etl.discard("report_index")
    sesion.fallos_pendientes = 1

    assert repo.existe_sesion("s1") is True
    assert sesion.lecturas_esquema == 2
    assert sesion.rollbacks == 1
    assert 'h."report_index"' not in sesion.consultas[-1]


def test_un_error_persistente_no_se_reintenta_indefinidamente():
    sesion = SesionFalsa(ESQUEMA_COMPLETO, fallos=5)
    repo = VisualizacionTemporalRepository(sesion)

    with pytest.raises(ProgrammingError):
        repo.existe_sesion("s1")

    assert len(sesion.consultas) == 2
