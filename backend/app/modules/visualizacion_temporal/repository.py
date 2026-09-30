"""
Repositorio del Módulo 2 — Capa 4, única frontera con la base de datos.

Reglas que cumple este archivo (`CLAUDE.md` reglas 2 y 4, `docs/02-arquitectura.md`):

- **Solo aquí hay SQL.** Ninguna otra capa del módulo importa SQLAlchemy.
- **Es el único archivo que conoce el esquema del Módulo 1.** Lee `handover_record` (y
  `etl_execution` para el nombre de la sesión) directamente, sin vistas intermedias. Si el ETL
  cambia su esquema, el impacto queda contenido aquí (ver "Adaptación al esquema del ETL").
- **Solo escribe en `eventos_handover`**, que es la única tabla propiedad del módulo. Las tablas
  del Módulo 1 se leen y nunca se modifican.
- No contiene reglas de negocio: no decide qué es un handover, solo trae filas y guarda filas.

Adaptación al esquema del ETL (decisión D-1, BLQ-21)
----------------------------------------------------
El esquema de `handover_record` sigue evolucionando (migraciones 002-005 del Módulo 1). Antes la
adaptación la hacía una vista generada con SQL dinámico, pero la vista se congelaba al crearse y
había que reejecutar el script a mano cada vez que el ETL añadía columnas; además bloqueaba los
`DROP COLUMN`/`ALTER TYPE` del Módulo 1.

Ahora el repositorio consulta `information_schema` y construye la consulta de mediciones con las
columnas que existan **en ese momento**: cada campo del contrato (`docs/09`) toma la columna
nueva del ETL y, si está vacía, la heredada (`cid ← cell_id`, `tech ← tecnologia`...). El
resultado se cachea `SEGUNDOS_CACHE_ESQUEMA` segundos y se invalida solo si una consulta falla por
una columna que ha desaparecido.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.modules.visualizacion_temporal.detector import HandoverDetectado, Medicion

logger = logging.getLogger(__name__)

# Tablas del Módulo 1 (solo lectura).
TABLA_MEDICIONES_ETL = "handover_record"
TABLA_EJECUCIONES_ETL = "etl_execution"

# Tablas y vistas propias del Módulo 2 (docs/sql/01 y 02).
TABLA_MEDICIONES_PRUEBA = "vt_medicion_prueba"
VISTA_EVENTOS = "v_vt_evento_detalle"

#: Cada cuánto se vuelve a mirar el esquema del ETL. Una consulta a `information_schema` es
#: barata, pero hacerla en cada petición añadiría un viaje de red a Supabase por endpoint.
SEGUNDOS_CACHE_ESQUEMA = 60.0

#: Columnas mínimas de `handover_record` sin las que las filas reales no pueden leerse.
_COLUMNAS_OBLIGATORIAS_ETL = frozenset({"id_registro", "execution_id", "timestamp_medicion"})

#: Parámetros RF del contrato, en el orden en que se informa su cobertura.
_PARAMETROS_RF = ("rsrp_dbm", "rsrq_db", "rssnr_db", "rscp_dbm", "rssi_dbm")

#: Columnas que el repositorio proyecta de las mediciones, en el orden del contrato.
_COLUMNAS_MEDICION = (
    "id_medicion",
    "sesion_id",
    "sesion_nombre",
    "report_index",
    "timestamp_medicion",
    "tech",
    "net_type",
    "cid",
    "node_id",
    "psc_pci",
    "lac_tac",
    "arfcn",
    "band",
    "rsrp_dbm",
    "rsrq_db",
    "rssnr_db",
    "rscp_dbm",
    "rssi_dbm",
    "data_state",
    "call_state",
)

#: Columnas de la fuente de mediciones: el contrato más la identidad de celda y el origen.
_COLUMNAS_FUENTE = _COLUMNAS_MEDICION + ("celda_clave", "origen")


# =========================================================================================
# Adaptación al esquema del ETL
# =========================================================================================


def _ref(columna: str) -> str:
    """Referencia a una columna de `handover_record`, siempre entrecomillada."""
    return f'h."{columna}"'


def construir_sql_mediciones(
    columnas_etl: frozenset[str] | set[str],
    columnas_ejecucion: frozenset[str] | set[str] = frozenset(),
    incluir_prueba: bool = True,
) -> str:
    """Construye el `SELECT` de mediciones a partir de las columnas que existen hoy.

    Función pura: recibe los nombres de columna de `handover_record` y de `etl_execution` y
    devuelve SQL. Los nombres que se concatenan salen siempre de las listas fijas de este
    archivo, nunca de la base, así que no hay riesgo de inyección.

    El resultado une dos orígenes bajo el mismo contrato y la misma forma de columnas:

    - `'real'`: `handover_record`, producida por el Módulo 1 (se omite si la tabla no existe o
      le faltan las columnas mínimas).
    - `'sintetico'`: `vt_medicion_prueba`, el recorrido de verdad conocida del Módulo 2.

    Mapeo de cada campo del contrato (columna nueva ← columna heredada):
    `tech ← tecnologia (1/2/3)`, `cid ← cell_id`, `lac_tac ← lac_tac_raw ← tac`,
    `arfcn ← earfcn`, `rsrq_db ← rsrq`, `rssnr_db ← rssnr`, y `rsrp/rscp/rssi ← rssi` según `tech`.
    """
    ramas: list[str] = []

    if _COLUMNAS_OBLIGATORIAS_ETL <= set(columnas_etl):
        ramas.append(_rama_real(set(columnas_etl), set(columnas_ejecucion)))

    if incluir_prueba:
        ramas.append(
            "SELECT "
            + ", ".join(f"p.{c}" for c in _COLUMNAS_MEDICION)
            + f", p.celda_clave, 'sintetico'::text AS origen FROM {TABLA_MEDICIONES_PRUEBA} p"
        )

    if not ramas:
        raise RuntimeError(
            f"No hay ninguna fuente de mediciones: falta la tabla {TABLA_MEDICIONES_ETL} "
            f"(o sus columnas mínimas) y la tabla {TABLA_MEDICIONES_PRUEBA}."
        )

    return "\nUNION ALL\n".join(ramas)


def _rama_real(columnas: set[str], columnas_ejecucion: set[str]) -> str:
    """`SELECT` de `handover_record` con el mapeo al contrato de docs/09."""

    def col(nombre: str, reserva: str = "NULL") -> str:
        return _ref(nombre) if nombre in columnas else reserva

    def primera(candidatas: tuple[str, ...], reserva: str = "NULL") -> str:
        refs = [_ref(c) for c in candidatas if c in columnas]
        if not refs:
            return reserva
        return refs[0] if len(refs) == 1 else f"COALESCE({', '.join(refs)})"

    # Tecnología: `tech` textual del ETL v2; en filas viejas se traduce el código `tecnologia`
    # (0 = sin señal -> NULL).
    tech_bruto = (
        "CASE h.\"tecnologia\" WHEN 1 THEN 'LTE' WHEN 2 THEN 'WCDMA' WHEN 3 THEN 'GSM' END"
        if "tecnologia" in columnas
        else "NULL"
    )
    tech = f'COALESCE(h."tech", {tech_bruto})' if "tech" in columnas else tech_bruto

    # Nombre de sesión: "Sesión <sesion_label> · <archivo> · <hoja>". La etiqueta puede vivir
    # en handover_record o en etl_execution según la versión del ETL.
    union_ejecucion = ""
    if "sesion_label" in columnas:
        etiqueta = 'h."sesion_label"::text'
    elif "sesion_label" in columnas_ejecucion and "execution_id" in columnas_ejecucion:
        etiqueta = 'x."sesion_label"::text'
        union_ejecucion = (
            f"LEFT JOIN {TABLA_EJECUCIONES_ETL} x ON x.\"execution_id\" = h.\"execution_id\""
        )
    else:
        etiqueta = "NULL::text"
    sesion_nombre = (
        "NULLIF(concat_ws(' · ', "
        f"CASE WHEN {etiqueta} ~ '^[0-9]+$' THEN 'Sesión ' || {etiqueta} ELSE {etiqueta} END, "
        f"{col('archivo_origen', 'NULL::text')}, {col('hoja_origen', 'NULL::text')}), '')"
    )

    # Columna genérica `rssi` de una iteración anterior del ETL: se enruta según la tecnología.
    rssi_bruto = col("rssi")

    proyeccion = {
        "id_medicion": 'h."id_registro"',
        "sesion_id": 'h."execution_id"',
        "sesion_nombre": sesion_nombre,
        "report_index": f"{col('report_index')}::integer",
        "timestamp_medicion": 'h."timestamp_medicion"',
        "tech": "t.tech",
        "net_type": f"{col('net_type')}::text",
        "cid": f"{primera(('cid', 'cell_id'))}::bigint",
        "node_id": f"{col('node_id')}::integer",
        "psc_pci": f"{col('psc_pci')}::integer",
        "lac_tac": f"{primera(('lac_tac_raw', 'lac_tac', 'tac'))}::integer",
        "arfcn": f"{primera(('arfcn', 'earfcn'))}::integer",
        "band": f"{col('band')}::integer",
        "rsrp_dbm": f"COALESCE({col('rsrp_dbm')}, CASE WHEN t.tech = 'LTE' THEN {rssi_bruto} END)::smallint",
        "rsrq_db": f"{primera(('rsrq_db', 'rsrq'))}::smallint",
        "rssnr_db": f"{primera(('rssnr_db', 'rssnr'))}::smallint",
        "rscp_dbm": f"COALESCE({col('rscp_dbm')}, CASE WHEN t.tech = 'WCDMA' THEN {rssi_bruto} END)::smallint",
        "rssi_dbm": f"COALESCE({col('rssi_dbm')}, CASE WHEN t.tech = 'GSM' THEN {rssi_bruto} END)::smallint",
        "data_state": f"{col('data_state')}::text",
        "call_state": f"{col('call_state')}::text",
    }
    interior = ",\n            ".join(f"{proyeccion[c]} AS {c}" for c in _COLUMNAS_MEDICION)

    # Identidad canónica de la celda: réplica de vt_celda_clave() y de detector.clave_de_celda.
    celda_clave = (
        "CASE WHEN r.cid IS NULL THEN NULL "
        "WHEN r.tech = 'LTE' AND r.node_id IS NOT NULL "
        "THEN 'LTE:' || (r.node_id::bigint * 256 + r.cid)::text "
        "ELSE COALESCE(r.tech, 'DESCONOCIDA') || ':' || COALESCE(r.lac_tac::text, '?') "
        "|| ':' || r.cid::text END"
    )

    return (
        "SELECT "
        + ", ".join(f"r.{c}" for c in _COLUMNAS_MEDICION)
        + f", {celda_clave} AS celda_clave, 'real'::text AS origen\n"
        + "  FROM (\n        SELECT\n            "
        + interior
        + f"\n          FROM {TABLA_MEDICIONES_ETL} h\n"
        + (f"          {union_ejecucion}\n" if union_ejecucion else "")
        + f"          CROSS JOIN LATERAL (SELECT ({tech})::text AS tech) t\n"
        + "  ) r"
    )


class _CacheEsquema:
    """SQL de mediciones ya construido, compartido entre peticiones y renovado cada cierto tiempo."""

    def __init__(self, segundos: float):
        self._segundos = segundos
        self._sql: str | None = None
        self._instante = 0.0
        self._cerrojo = threading.Lock()

    def obtener(self, db: Session) -> str:
        with self._cerrojo:
            if self._sql is not None and time.monotonic() - self._instante < self._segundos:
                return self._sql

        sql = self._construir(db)

        with self._cerrojo:
            if sql != self._sql:
                logger.info("Consulta de mediciones (re)construida según el esquema actual del ETL")
            self._sql = sql
            self._instante = time.monotonic()
        return sql

    def invalidar(self) -> None:
        with self._cerrojo:
            self._sql = None

    @staticmethod
    def _construir(db: Session) -> str:
        filas = db.execute(
            text(
                """
                SELECT table_name, column_name
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name = ANY(:tablas)
                """
            ),
            {"tablas": [TABLA_MEDICIONES_ETL, TABLA_EJECUCIONES_ETL, TABLA_MEDICIONES_PRUEBA]},
        ).all()

        por_tabla: dict[str, set[str]] = {}
        for tabla, columna in filas:
            por_tabla.setdefault(tabla, set()).add(columna)

        columnas_etl = por_tabla.get(TABLA_MEDICIONES_ETL, set())
        if not _COLUMNAS_OBLIGATORIAS_ETL <= columnas_etl:
            logger.warning(
                "%s no existe o le faltan columnas mínimas; solo se leerán datos sintéticos",
                TABLA_MEDICIONES_ETL,
            )

        return construir_sql_mediciones(
            columnas_etl,
            por_tabla.get(TABLA_EJECUCIONES_ETL, set()),
            incluir_prueba=TABLA_MEDICIONES_PRUEBA in por_tabla,
        )


_cache_esquema = _CacheEsquema(SEGUNDOS_CACHE_ESQUEMA)


def invalidar_cache_esquema() -> None:
    """Fuerza a releer el esquema del ETL en la próxima consulta."""
    _cache_esquema.invalidar()


class VisualizacionTemporalRepository:
    """Acceso a datos del Módulo 2."""

    def __init__(self, db: Session):
        self._db = db

    def _consultar_mediciones(self, plantilla: Callable[[str], str], parametros: dict):
        """Ejecuta una consulta sobre la fuente de mediciones, adaptada al esquema del ETL.

        `plantilla` recibe la fuente ya lista para ir en un `FROM` (con alias `m`) y devuelve el
        SQL completo. Si la consulta falla porque el Módulo 1 acaba de quitar o renombrar una
        columna que la caché aún creía viva, se relee el esquema y se reintenta una sola vez.
        """
        for intento in range(2):
            fuente = f"(\n{_cache_esquema.obtener(self._db)}\n) AS m"
            try:
                return self._db.execute(text(plantilla(fuente)), parametros)
            except ProgrammingError:
                self._db.rollback()
                if intento:
                    raise
                logger.warning("El esquema del ETL cambió durante la consulta; se relee")
                invalidar_cache_esquema()

    # -------------------------------------------------------------------------------------
    # Lectura
    # -------------------------------------------------------------------------------------

    def existe_sesion(self, sesion_id: str) -> bool:
        """Comprueba si la sesión tiene alguna medición, sea real o sintética."""
        return (
            self._consultar_mediciones(
                lambda fuente: f"SELECT 1 FROM {fuente} WHERE sesion_id = :sesion_id LIMIT 1",
                {"sesion_id": sesion_id},
            ).first()
            is not None
        )

    @staticmethod
    def _sesiones(filtros) -> list[str]:
        """Sesiones del filtro: la lista completa si la hay, o la única `sesion_id`."""
        return list(getattr(filtros, "sesion_ids", None) or [filtros.sesion_id])

    def _clausula_filtros(self, filtros) -> tuple[list[str], dict]:
        """Traduce el bloque de filtros común a condiciones SQL parametrizadas (HU-C2-006).

        Todo va como parámetro ligado: no se concatena ni un solo valor en el SQL. La sesión se
        compara como texto (`::text`) para que la lista funcione igual si la columna es `uuid`.
        """
        condiciones = ["sesion_id::text = ANY(:sesion_ids)"]
        parametros: dict[str, object] = {"sesion_ids": self._sesiones(filtros)}

        if getattr(filtros, "desde", None) is not None:
            condiciones.append("timestamp_medicion >= :desde")
            parametros["desde"] = filtros.desde
        if getattr(filtros, "hasta", None) is not None:
            condiciones.append("timestamp_medicion <= :hasta")
            parametros["hasta"] = filtros.hasta

        # Filtro de hora del día: se aplica a cada día del rango, no una sola vez.
        if getattr(filtros, "hora_inicio", None) is not None:
            condiciones.append("timestamp_medicion::time >= :hora_inicio")
            parametros["hora_inicio"] = filtros.hora_inicio
        if getattr(filtros, "hora_fin", None) is not None:
            condiciones.append("timestamp_medicion::time <= :hora_fin")
            parametros["hora_fin"] = filtros.hora_fin

        tecnologias = getattr(filtros, "tecnologia", None) or []
        if tecnologias:
            condiciones.append("tech = ANY(:tecnologias)")
            parametros["tecnologias"] = [
                t.value if hasattr(t, "value") else str(t) for t in tecnologias
            ]

        return condiciones, parametros

    def obtener_mediciones(
        self,
        sesion_id: str,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> list[Medicion]:
        """Trae las mediciones de una sesión, ya ordenadas.

        El orden `(timestamp_medicion, report_index)` es el que hace reproducible la detección:
        la aplicación muestrea a 1 Hz y puede emitir varias filas en el mismo segundo (BLQ-08).
        `NULLS LAST` evita que las filas sin `report_index` (esquema actual del Módulo 1) se
        cuelen por delante.
        """
        return self.obtener_mediciones_filtradas(
            SimpleNamespace(sesion_id=sesion_id, desde=desde, hasta=hasta)
        )

    def obtener_mediciones_filtradas(self, filtros) -> list[Medicion]:
        """Igual que `obtener_mediciones` pero con el bloque de filtros completo (HU-C2-006)."""
        condiciones, parametros = self._clausula_filtros(filtros)

        filas = self._consultar_mediciones(
            lambda fuente: f"""
            SELECT {", ".join(_COLUMNAS_MEDICION)}
              FROM {fuente}
             WHERE {" AND ".join(condiciones)}
             ORDER BY timestamp_medicion ASC, report_index ASC NULLS LAST
            """,
            parametros,
        ).mappings().all()
        return [self._a_medicion(fila) for fila in filas]

    def listar_sesiones(self) -> list[dict]:
        """Sesiones disponibles, con sus totales. Alimenta el selector del header (HU-C2-006).

        El Módulo 1 no expone ningún listado de ejecuciones (BLQ-06), así que el Módulo 2 lo
        construye desde su propia fuente de mediciones.
        """
        resultado = self._consultar_mediciones(
            lambda fuente: f"""
            SELECT m.sesion_id::text                       AS sesion_id,
                   min(m.sesion_nombre)                    AS sesion_nombre,
                   min(m.timestamp_medicion)               AS inicio,
                   max(m.timestamp_medicion)               AS fin,
                   count(*)                                AS n_mediciones,
                   count(DISTINCT m.celda_clave)           AS n_celdas,
                   array_agg(DISTINCT m.tech)
                     FILTER (WHERE m.tech IS NOT NULL)     AS tecnologias,
                   min(m.origen)                           AS origen,
                   COALESCE(
                       (SELECT count(*) FROM eventos_handover e
                         WHERE e.sesion_id = m.sesion_id), 0
                   )                                       AS n_handovers
              FROM {fuente}
             GROUP BY m.sesion_id
             ORDER BY min(m.timestamp_medicion) DESC
            """,
            {},
        )
        return [dict(fila) for fila in resultado.mappings()]

    def listar_handovers(
        self,
        filtros,
        page: int = 1,
        page_size: int = 50,
        orden: str = "asc",
    ) -> tuple[int, list[dict]]:
        """Página de eventos para la tabla de HU-C2-009. Devuelve (total, filas)."""
        condiciones = ["sesion_id::text = ANY(:sesion_ids)"]
        parametros: dict[str, object] = {"sesion_ids": self._sesiones(filtros)}

        if getattr(filtros, "desde", None) is not None:
            condiciones.append("timestamp_evento >= :desde")
            parametros["desde"] = filtros.desde
        if getattr(filtros, "hasta", None) is not None:
            condiciones.append("timestamp_evento <= :hasta")
            parametros["hasta"] = filtros.hasta
        if getattr(filtros, "hora_inicio", None) is not None:
            condiciones.append("timestamp_evento::time >= :hora_inicio")
            parametros["hora_inicio"] = filtros.hora_inicio
        if getattr(filtros, "hora_fin", None) is not None:
            condiciones.append("timestamp_evento::time <= :hora_fin")
            parametros["hora_fin"] = filtros.hora_fin

        tecnologias = getattr(filtros, "tecnologia", None) or []
        if tecnologias:
            # Un evento entra si su origen o su destino usan alguna de las tecnologías pedidas.
            condiciones.append(
                "(celda_origen_tech = ANY(:tecnologias) OR celda_destino_tech = ANY(:tecnologias))"
            )
            parametros["tecnologias"] = [
                t.value if hasattr(t, "value") else str(t) for t in tecnologias
            ]

        where = " AND ".join(condiciones)

        total = self._db.execute(
            text(f"SELECT count(*) FROM {VISTA_EVENTOS} WHERE {where}"), parametros
        ).scalar_one()

        direccion = "DESC" if str(orden).lower() == "desc" else "ASC"
        parametros_pagina = {
            **parametros,
            "limite": page_size,
            "desplazamiento": max(0, (page - 1) * page_size),
        }

        filas = self._db.execute(
            text(
                f"""
                SELECT * FROM {VISTA_EVENTOS}
                 WHERE {where}
                 ORDER BY timestamp_evento {direccion}, id_evento
                 LIMIT :limite OFFSET :desplazamiento
                """
            ),
            parametros_pagina,
        ).mappings()

        return int(total), [dict(fila) for fila in filas]

    def obtener_handover(self, id_evento: str) -> dict | None:
        """Un evento concreto, para la ventana PRE/POST de HU-C2-005."""
        fila = self._db.execute(
            text(f"SELECT * FROM {VISTA_EVENTOS} WHERE id_evento = :id_evento"),
            {"id_evento": id_evento},
        ).mappings().first()
        return dict(fila) if fila else None

    def obtener_mediciones_en_rango(
        self,
        sesion_id: str,
        t_inicio: datetime,
        t_fin: datetime,
    ) -> list[Medicion]:
        """Mediciones dentro de una ventana temporal concreta (HU-C2-005)."""
        return self.obtener_mediciones(sesion_id, desde=t_inicio, hasta=t_fin)

    def obtener_cobertura_parametros(self, sesion_id: str) -> list[dict]:
        """Cuántas medidas válidas hay de cada parámetro RF en la sesión.

        Sostiene el aviso explícito de "sin datos válidos" de la interfaz (decisión D-5).
        Se agrupa solo por parámetro: una ejecución del ETL con varias hojas es una única sesión,
        y agrupar también por nombre partiría el denominador.
        """
        valores = ", ".join(f"('{p}', m.{p})" for p in _PARAMETROS_RF)
        resultado = self._consultar_mediciones(
            lambda fuente: f"""
            SELECT p.parametro,
                   count(p.valor)                                            AS n_validos,
                   count(*)                                                  AS n_mediciones,
                   round(100.0 * count(p.valor) / NULLIF(count(*), 0), 1)    AS pct_validos
              FROM {fuente}
             CROSS JOIN LATERAL (VALUES {valores}) AS p(parametro, valor)
             WHERE m.sesion_id = :sesion_id
             GROUP BY p.parametro
             ORDER BY p.parametro
            """,
            {"sesion_id": sesion_id},
        )
        return [dict(fila) for fila in resultado.mappings()]

    # -------------------------------------------------------------------------------------
    # Escritura — solo eventos_handover
    # -------------------------------------------------------------------------------------

    def borrar_handovers_de_sesion(self, sesion_id: str) -> int:
        """Borra los eventos previos de una sesión. Hace idempotente la re-detección."""
        resultado = self._db.execute(
            text("DELETE FROM eventos_handover WHERE sesion_id = :sesion_id"),
            {"sesion_id": sesion_id},
        )
        self._db.commit()
        return resultado.rowcount or 0

    def guardar_handovers(
        self,
        eventos: list[HandoverDetectado],
        parametros_deteccion: dict,
    ) -> int:
        """Inserta los eventos detectados en lote. Devuelve cuántos se guardaron."""
        if not eventos:
            return 0

        sql = text(
            """
            INSERT INTO eventos_handover (
                id_evento, sesion_id, sesion_nombre,
                timestamp_evento, report_index_evento,
                celda_origen_clave, celda_origen_cid, celda_origen_node_id,
                celda_origen_psc_pci, celda_origen_arfcn, celda_origen_tech,
                celda_destino_clave, celda_destino_cid, celda_destino_node_id,
                celda_destino_psc_pci, celda_destino_arfcn, celda_destino_tech,
                medicion_previa_id, medicion_posterior_id,
                tipo_evento, ping_pong, tipo_tecnologia, confianza, data_state_evento,
                delta_rsrp_db, delta_rsrq_db, delta_rssnr_db, delta_rscp_db, delta_rssi_db,
                duracion_permanencia_s, muestras_confirmacion,
                parametros_deteccion
            ) VALUES (
                :id_evento, :sesion_id, :sesion_nombre,
                :timestamp_evento, :report_index_evento,
                :celda_origen_clave, :celda_origen_cid, :celda_origen_node_id,
                :celda_origen_psc_pci, :celda_origen_arfcn, :celda_origen_tech,
                :celda_destino_clave, :celda_destino_cid, :celda_destino_node_id,
                :celda_destino_psc_pci, :celda_destino_arfcn, :celda_destino_tech,
                :medicion_previa_id, :medicion_posterior_id,
                :tipo_evento, :ping_pong, :tipo_tecnologia, :confianza, :data_state_evento,
                :delta_rsrp_db, :delta_rsrq_db, :delta_rssnr_db, :delta_rscp_db, :delta_rssi_db,
                :duracion_permanencia_s, :muestras_confirmacion,
                CAST(:parametros_deteccion AS JSONB)
            )
            ON CONFLICT ON CONSTRAINT uq_ho_evento DO NOTHING
            """
        )

        import json

        parametros_json = json.dumps(parametros_deteccion, sort_keys=True)
        filas = [
            {
                "id_evento": str(uuid.uuid4()),
                "sesion_id": evento.sesion_id,
                "sesion_nombre": evento.sesion_nombre,
                "timestamp_evento": evento.timestamp_evento,
                "report_index_evento": evento.report_index_evento,
                "celda_origen_clave": evento.celda_origen_clave,
                "celda_origen_cid": evento.celda_origen_cid,
                "celda_origen_node_id": evento.celda_origen_node_id,
                "celda_origen_psc_pci": evento.celda_origen_psc_pci,
                "celda_origen_arfcn": evento.celda_origen_arfcn,
                "celda_origen_tech": evento.celda_origen_tech,
                "celda_destino_clave": evento.celda_destino_clave,
                "celda_destino_cid": evento.celda_destino_cid,
                "celda_destino_node_id": evento.celda_destino_node_id,
                "celda_destino_psc_pci": evento.celda_destino_psc_pci,
                "celda_destino_arfcn": evento.celda_destino_arfcn,
                "celda_destino_tech": evento.celda_destino_tech,
                "medicion_previa_id": evento.medicion_previa_id,
                "medicion_posterior_id": evento.medicion_posterior_id,
                "tipo_evento": evento.tipo_evento,
                "ping_pong": evento.ping_pong,
                "tipo_tecnologia": evento.tipo_tecnologia,
                "confianza": evento.confianza,
                "data_state_evento": evento.data_state_evento,
                "delta_rsrp_db": evento.delta_rsrp_db,
                "delta_rsrq_db": evento.delta_rsrq_db,
                "delta_rssnr_db": evento.delta_rssnr_db,
                "delta_rscp_db": evento.delta_rscp_db,
                "delta_rssi_db": evento.delta_rssi_db,
                "duracion_permanencia_s": evento.duracion_permanencia_s,
                "muestras_confirmacion": evento.muestras_confirmacion,
                "parametros_deteccion": parametros_json,
            }
            for evento in eventos
        ]

        self._db.execute(sql, filas)
        self._db.commit()
        return len(filas)

    # -------------------------------------------------------------------------------------
    # Conversión
    # -------------------------------------------------------------------------------------

    @staticmethod
    def _a_medicion(fila) -> Medicion:
        """Convierte una fila de mediciones en el objeto puro que consume el detector."""
        return Medicion(
            id_medicion=str(fila["id_medicion"]),
            sesion_id=str(fila["sesion_id"]),
            sesion_nombre=fila["sesion_nombre"],
            report_index=fila["report_index"],
            timestamp_medicion=fila["timestamp_medicion"],
            tech=fila["tech"],
            net_type=fila["net_type"],
            cid=fila["cid"],
            node_id=fila["node_id"],
            psc_pci=fila["psc_pci"],
            lac_tac=fila["lac_tac"],
            arfcn=fila["arfcn"],
            band=fila["band"],
            rsrp_dbm=fila["rsrp_dbm"],
            rsrq_db=fila["rsrq_db"],
            rssnr_db=fila["rssnr_db"],
            rscp_dbm=fila["rscp_dbm"],
            rssi_dbm=fila["rssi_dbm"],
            data_state=fila["data_state"],
            call_state=fila["call_state"],
        )
