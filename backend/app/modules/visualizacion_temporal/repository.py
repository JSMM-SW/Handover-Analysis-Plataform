"""
Repositorio del Módulo 2 — Capa 4, única frontera con la base de datos.

Reglas que cumple este archivo (`CLAUDE.md` reglas 2 y 4, `docs/02-arquitectura.md`):

- **Solo aquí hay SQL.** Ninguna otra capa del módulo importa SQLAlchemy.
- **Es el único archivo que conoce el esquema del Módulo 1.** Lee `handover_record` (y
  `etl_execution` para el nombre de la sesión) directamente, sin vistas intermedias. Si el ETL
  cambia su esquema, el impacto queda contenido aquí (ver "Adaptación al esquema del ETL").
- **Solo escribe en `eventos_handover`**, que es la única tabla propiedad del módulo. Las tablas
  del Módulo 1 se leen y nunca se modifican.
- **No depende de vistas.** También `eventos_handover` se lee directamente: una vista es un objeto
  más que puede desaparecer al migrar la base, y su falta tumbaba la tabla de eventos (BLQ-23).
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

Caché de mediciones por sesión
------------------------------
Con la Sesión 4 (86 388 mediciones) la consulta tarda ~0,2 s en Supabase, pero **bajar las filas**
cuesta de 6 a 20 s: son ~19 MB en el protocolo de PostgreSQL. Y al elegir una sesión la interfaz
pide a la vez series, tramos, resumen, histograma y detección, de modo que la sesión se descargaba
cinco o seis veces en paralelo por la misma conexión y todas superaban los 30 s del navegador.

Ahora las mediciones de cada sesión se descargan **una sola vez** y se guardan en memoria
(`_CacheMediciones`); los filtros de fecha, franja horaria y tecnología se aplican sobre ellas
(`filtrar_mediciones`). Antes de reutilizar una sesión se compara su huella con la de la base, así
que si el Módulo 1 borra, añade o corrige filas, la sesión se vuelve a leer.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from datetime import time as dt_time
from itertools import chain
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.modules.visualizacion_temporal.detector import HandoverDetectado, Medicion

logger = logging.getLogger(__name__)

# Tablas del Módulo 1 (solo lectura).
TABLA_MEDICIONES_ETL = "handover_record"
TABLA_EJECUCIONES_ETL = "etl_execution"

# Tabla propia del Módulo 2 (docs/sql/01).
TABLA_EVENTOS = "eventos_handover"

#: Cada cuánto se vuelve a mirar el esquema del ETL. Una consulta a `information_schema` es
#: barata, pero hacerla en cada petición añadiría un viaje de red a Supabase por endpoint.
SEGUNDOS_CACHE_ESQUEMA = 60.0

#: Mediciones que puede guardar en total la caché de sesiones (~0,55 KB cada una: la Sesión 4,
#: con 86 388, ocupa unos 47 MB). Cuando se pasa, se descartan las sesiones usadas hace más
#: tiempo; la última siempre se queda, aunque sola supere el límite.
MAX_MEDICIONES_EN_CACHE = 300_000

#: Segundos durante los que una sesión recién comprobada se sirve sin volver a mirar su huella.
#: Cubre la ráfaga de peticiones que lanza la interfaz al elegir una sesión, que así no paga cada
#: una su viaje de ida y vuelta a Supabase.
SEGUNDOS_CONFIANZA_CACHE = 30.0

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


# =========================================================================================
# Adaptación al esquema del ETL
# =========================================================================================


def _ref(columna: str) -> str:
    """Referencia a una columna de `handover_record`, siempre entrecomillada."""
    return f'h."{columna}"'


def construir_sql_mediciones(
    columnas_etl: frozenset[str] | set[str],
    columnas_ejecucion: frozenset[str] | set[str] = frozenset(),
) -> str:
    """Construye el `SELECT` de mediciones a partir de las columnas que existen hoy.

    Función pura: recibe los nombres de columna de `handover_record` y de `etl_execution` y
    devuelve SQL. Los nombres que se concatenan salen siempre de las listas fijas de este
    archivo, nunca de la base, así que no hay riesgo de inyección.

    La única fuente es `handover_record`, producida por el Módulo 1.

    Mapeo de cada campo del contrato (columna nueva ← columna heredada):
    `tech ← tecnologia (1/2/3)`, `cid ← cell_id`, `lac_tac ← lac_tac_raw ← tac`,
    `arfcn ← earfcn`, `rsrq_db ← rsrq`, `rssnr_db ← rssnr`, y `rssi_dbm ← rssi` (alias del contrato, sin reinterpretar la medida).
    """
    if not _COLUMNAS_OBLIGATORIAS_ETL <= set(columnas_etl):
        raise RuntimeError(
            f"No hay fuente de mediciones: falta la tabla {TABLA_MEDICIONES_ETL} o alguna de sus "
            f"columnas mínimas ({', '.join(sorted(_COLUMNAS_OBLIGATORIAS_ETL))})."
        )

    return _construir_sql_handover_record(set(columnas_etl), set(columnas_ejecucion))


def _construir_sql_handover_record(columnas: set[str], columnas_ejecucion: set[str]) -> str:
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

    # RSSI original para todas las tecnologias. RSRP procede de rssi_strongest segun la verificacion del usuario para NetMonitor.
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
        "rsrp_dbm": f"{col('rsrp')}::smallint",
        "rsrq_db": f"{primera(('rsrq_db', 'rsrq'))}::smallint",
        "rssnr_db": f"{primera(('rssnr_db', 'rssnr'))}::smallint",
        "rscp_dbm": "NULL::smallint",
        "rssi_dbm": f"{rssi_bruto}::smallint",
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
        + f", {celda_clave} AS celda_clave\n"
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
            {"tablas": [TABLA_MEDICIONES_ETL, TABLA_EJECUCIONES_ETL]},
        ).all()

        por_tabla: dict[str, set[str]] = {}
        for tabla, columna in filas:
            por_tabla.setdefault(tabla, set()).add(columna)

        return construir_sql_mediciones(
            por_tabla.get(TABLA_MEDICIONES_ETL, set()),
            por_tabla.get(TABLA_EJECUCIONES_ETL, set()),
        )


_cache_esquema = _CacheEsquema(SEGUNDOS_CACHE_ESQUEMA)


@dataclass
class _SesionEnCache:
    huella: tuple
    mediciones: list[Medicion]
    comprobada: float


class _CacheMediciones:
    """Mediciones completas de las últimas sesiones consultadas, compartidas entre peticiones.

    Las mediciones de una sesión no cambian una vez que el ETL la ha cargado, así que basta con
    descargarlas una vez. Dos garantías:

    - **Una sola descarga por sesión a la vez.** Las peticiones que piden una sesión mientras se
      está descargando esperan a esa descarga y la reutilizan, en lugar de lanzar la suya.
    - **Nunca se sirven datos viejos más de `segundos_confianza`.** Pasado ese tiempo se vuelve a
      leer la huella de la sesión en la base, y si no coincide se descarga de nuevo.
    """

    def __init__(self, max_mediciones: int, segundos_confianza: float):
        self._max_mediciones = max_mediciones
        self._segundos_confianza = segundos_confianza
        self._sesiones: OrderedDict[str, _SesionEnCache] = OrderedDict()
        self._cerrojos: dict[str, threading.Lock] = {}
        self._cerrojo = threading.Lock()

    def obtener(
        self,
        sesion_id: str,
        leer_huella: Callable[[], tuple],
        leer_mediciones: Callable[[], list[Medicion]],
    ) -> list[Medicion]:
        """Mediciones de la sesión, de la caché si siguen vigentes o recién leídas si no.

        `leer_huella` devuelve una tupla cuyo primer elemento es el número de filas; con 0 filas
        la sesión no existe (o ya no) y no se guarda nada.
        """
        with self._cerrojo:
            cerrojo_sesion = self._cerrojos.setdefault(sesion_id, threading.Lock())

        with cerrojo_sesion:
            with self._cerrojo:
                entrada = self._sesiones.get(sesion_id)
                if entrada is not None:
                    self._sesiones.move_to_end(sesion_id)

            if entrada is not None and time.monotonic() - entrada.comprobada < self._segundos_confianza:
                return entrada.mediciones

            huella = leer_huella()
            if entrada is not None and entrada.huella == huella:
                entrada.comprobada = time.monotonic()
                return entrada.mediciones

            mediciones = leer_mediciones() if huella[0] else []
            with self._cerrojo:
                if mediciones:
                    self._sesiones[sesion_id] = _SesionEnCache(huella, mediciones, time.monotonic())
                    self._sesiones.move_to_end(sesion_id)
                    self._recortar()
                else:
                    self._sesiones.pop(sesion_id, None)
            return mediciones

    def _recortar(self) -> None:
        """Descarta las sesiones usadas hace más tiempo hasta volver al límite de mediciones."""
        total = sum(len(s.mediciones) for s in self._sesiones.values())
        while total > self._max_mediciones and len(self._sesiones) > 1:
            _, descartada = self._sesiones.popitem(last=False)
            total -= len(descartada.mediciones)

    def vaciar(self) -> None:
        with self._cerrojo:
            self._sesiones.clear()


_cache_mediciones = _CacheMediciones(MAX_MEDICIONES_EN_CACHE, SEGUNDOS_CONFIANZA_CACHE)


def invalidar_cache_esquema() -> None:
    """Fuerza a releer el esquema del ETL en la próxima consulta.

    También olvida las mediciones guardadas: se leyeron con la consulta del esquema anterior.
    """
    _cache_esquema.invalidar()
    _cache_mediciones.vaciar()


def _instante(valor: datetime | None) -> datetime | None:
    """Una fecha sin zona se toma en UTC, que es como la interpreta la sesión de Supabase."""
    if valor is None or valor.tzinfo is not None:
        return valor
    return valor.replace(tzinfo=timezone.utc)


def _hora_sin_zona(valor: dt_time | None) -> dt_time | None:
    return valor.replace(tzinfo=None) if valor is not None else None


def filtrar_mediciones(mediciones: list[Medicion], filtros) -> list[Medicion]:
    """Aplica en memoria el bloque de filtros común (HU-C2-006). Devuelve siempre una lista nueva.

    Es la réplica del `WHERE` que antes llevaba la consulta:

    - `desde` y `hasta` acotan el instante, ambos incluidos.
    - La franja horaria se compara **en la zona del usuario** y se aplica a cada día del rango:
      con la zona `America/Guayaquil`, 16:00-17:00 son las 16:00-17:00 de Ecuador, no de UTC.
    - Las tecnologías se comparan con `tech` tal cual. Una medición sin tecnología no pasa ningún
      filtro de tecnología, igual que `NULL = ANY(...)` en SQL.
    """
    desde = _instante(getattr(filtros, "desde", None))
    hasta = _instante(getattr(filtros, "hasta", None))
    hora_inicio = _hora_sin_zona(getattr(filtros, "hora_inicio", None))
    hora_fin = _hora_sin_zona(getattr(filtros, "hora_fin", None))
    tecnologias = {
        t.value if hasattr(t, "value") else str(t)
        for t in getattr(filtros, "tecnologia", None) or []
    }
    zona = (
        ZoneInfo(getattr(filtros, "zona_horaria", None) or "UTC")
        if hora_inicio is not None or hora_fin is not None
        else None
    )

    if desde is None and hasta is None and zona is None and not tecnologias:
        return list(mediciones)

    def pasa(medicion: Medicion) -> bool:
        instante = medicion.timestamp_medicion
        if desde is not None and instante < desde:
            return False
        if hasta is not None and instante > hasta:
            return False
        if tecnologias and medicion.tech not in tecnologias:
            return False
        if zona is not None:
            hora_local = instante.astimezone(zona).time()
            if hora_inicio is not None and hora_local < hora_inicio:
                return False
            if hora_fin is not None and hora_local > hora_fin:
                return False
        return True

    return [m for m in mediciones if pasa(m)]


def _orden_temporal(medicion: Medicion) -> tuple:
    """`ORDER BY timestamp_medicion, report_index NULLS LAST`, para juntar varias sesiones."""
    return (
        medicion.timestamp_medicion,
        medicion.report_index is None,
        medicion.report_index or 0,
    )


def _texto_compartido(valor: str | None) -> str | None:
    """Comparte entre filas los textos que se repiten (`LTE`, `CONNECTED`...) para ahorrar memoria."""
    return sys.intern(valor) if isinstance(valor, str) else valor


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
        """Comprueba si la sesión tiene alguna medición."""
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

    @staticmethod
    def _condiciones_de_hora(filtros, columna: str, parametros: dict) -> list[str]:
        """Filtro de hora del día, aplicado a cada día del rango y no una sola vez.

        La hora se compara **en la zona del usuario**. La columna es `timestamptz` y la sesión de
        Supabase trabaja en UTC: un `columna::time` a secas daría la hora UTC, y la franja de
        16:00 a 17:00 que el usuario escribe en Ecuador (UTC−5) buscaría en realidad de 11:00 a
        12:00 locales y no encontraría nada.
        """
        condiciones = []
        hora_local = f"({columna} AT TIME ZONE :zona_horaria)::time"
        if getattr(filtros, "hora_inicio", None) is not None:
            condiciones.append(f"{hora_local} >= :hora_inicio")
            parametros["hora_inicio"] = filtros.hora_inicio
        if getattr(filtros, "hora_fin", None) is not None:
            condiciones.append(f"{hora_local} <= :hora_fin")
            parametros["hora_fin"] = filtros.hora_fin
        if condiciones:
            parametros["zona_horaria"] = getattr(filtros, "zona_horaria", None) or "UTC"
        return condiciones

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
        """Igual que `obtener_mediciones` pero con el bloque de filtros completo (HU-C2-006).

        Cada sesión sale de la caché (se descarga entera la primera vez) y los filtros se aplican
        en memoria. Con varias sesiones se mezclan en un único orden temporal.
        """
        listas = [self._mediciones_de_sesion(s) for s in self._sesiones(filtros)]
        mediciones = (
            listas[0]
            if len(listas) == 1
            else sorted(chain.from_iterable(listas), key=_orden_temporal)
        )
        return filtrar_mediciones(mediciones, filtros)

    def _mediciones_de_sesion(self, sesion_id: str) -> list[Medicion]:
        """Todas las mediciones de una sesión, a través de la caché. No modificar la lista."""
        return _cache_mediciones.obtener(
            sesion_id,
            leer_huella=lambda: self._leer_huella(sesion_id),
            leer_mediciones=lambda: self._leer_mediciones_de_sesion(sesion_id),
        )

    def _leer_huella(self, sesion_id: str) -> tuple:
        """Cuántas filas tiene la sesión en la base y la versión más reciente de cualquiera de ellas.

        `xmin` identifica la transacción que escribió cada fila, así que cambia con cada INSERT o
        UPDATE: si el Módulo 1 borra, añade o corrige mediciones de la sesión, la huella cambia.
        Recorre el índice de `execution_id` y cuesta unos milisegundos.
        """
        fila = self._db.execute(
            text(
                f"""
                SELECT count(*), max(h.xmin::text::bigint)
                  FROM {TABLA_MEDICIONES_ETL} h
                 WHERE h."execution_id" = :sesion_id
                """
            ),
            {"sesion_id": sesion_id},
        ).one()
        return int(fila[0]), fila[1]

    def _leer_mediciones_de_sesion(self, sesion_id: str) -> list[Medicion]:
        """Descarga todas las mediciones de una sesión, ordenadas.

        Lo caro es lo que viaja por la red, así que no se repite en cada fila lo que es igual en
        toda la sesión: su identificador y, cuando es único, su nombre (solo un libro de Excel
        con varias hojas da más de uno). Con la Sesión 4 eso reduce la descarga a la mitad.

        La sesión se compara con `=` y no como texto: así PostgreSQL usa el índice de
        `execution_id` en lugar de recorrer la tabla entera.
        """
        identidades = self._consultar_mediciones(
            lambda fuente: f"""
            SELECT DISTINCT m.sesion_id::text, m.sesion_nombre
              FROM {fuente}
             WHERE m.sesion_id = :sesion_id
            """,
            {"sesion_id": sesion_id},
        ).all()
        if not identidades:
            return []

        id_canonico = identidades[0][0]
        nombre_unico = len(identidades) == 1
        columnas = [
            c
            for c in _COLUMNAS_MEDICION
            if c != "sesion_id" and not (nombre_unico and c == "sesion_nombre")
        ]

        filas = self._consultar_mediciones(
            lambda fuente: f"""
            SELECT {", ".join(columnas)}
              FROM {fuente}
             WHERE m.sesion_id = :sesion_id
             ORDER BY m.timestamp_medicion ASC, m.report_index ASC NULLS LAST
            """,
            {"sesion_id": sesion_id},
        ).mappings()

        nombre = _texto_compartido(identidades[0][1]) if nombre_unico else None
        return [self._a_medicion(fila, id_canonico, nombre) for fila in filas]

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
                   COALESCE(
                       (SELECT count(*) FROM {TABLA_EVENTOS} e
                         WHERE e.sesion_id = m.sesion_id), 0
                   )                                       AS n_handovers
              FROM {fuente}
             GROUP BY m.sesion_id
             ORDER BY min(m.timestamp_medicion) DESC
            """,
            {},
        )
        return [dict(fila) for fila in resultado.mappings()]

    def contar_mediciones_por_minuto(self, sesion_ids: list[str], zona_horaria: str) -> list[dict]:
        """Mediciones de cada minuto con datos, en la hora local de `zona_horaria`.

        Es la materia prima del calendario: de aquí salen los días con datos y sus franjas
        horarias. Se agrupa por minuto y no se devuelven las filas, así que la respuesta es
        pequeña aunque la sesión tenga decenas de miles de mediciones.
        """
        resultado = self._consultar_mediciones(
            lambda fuente: f"""
            SELECT (m.timestamp_medicion AT TIME ZONE :zona_horaria)::date                    AS fecha,
                   date_trunc('minute', m.timestamp_medicion AT TIME ZONE :zona_horaria)::time AS minuto,
                   count(*)                                                                 AS n_mediciones
              FROM {fuente}
             WHERE m.sesion_id::text = ANY(:sesion_ids)
             GROUP BY 1, 2
             ORDER BY 1, 2
            """,
            {"sesion_ids": list(sesion_ids), "zona_horaria": zona_horaria},
        )
        return [dict(fila) for fila in resultado.mappings()]

    def contar_handovers_por_dia(self, sesion_ids: list[str], zona_horaria: str) -> list[dict]:
        """Handovers detectados en cada día local, para señalarlos en el calendario."""
        resultado = self._db.execute(
            text(
                f"""
                SELECT (timestamp_evento AT TIME ZONE :zona_horaria)::date AS fecha,
                       count(*)                                           AS n_handovers
                  FROM {TABLA_EVENTOS}
                 WHERE sesion_id::text = ANY(:sesion_ids)
                 GROUP BY 1
                """
            ),
            {"sesion_ids": list(sesion_ids), "zona_horaria": zona_horaria},
        )
        return [dict(fila) for fila in resultado.mappings()]

    def listar_tecnologias(self, sesion_ids: list[str]) -> list[str]:
        """Tecnologías que aparecen en las mediciones de las sesiones, tal como las guarda el ETL."""
        resultado = self._consultar_mediciones(
            lambda fuente: f"""
            SELECT DISTINCT m.tech
              FROM {fuente}
             WHERE m.sesion_id::text = ANY(:sesion_ids)
               AND m.tech IS NOT NULL
             ORDER BY m.tech
            """,
            {"sesion_ids": list(sesion_ids)},
        )
        return [fila[0] for fila in resultado]

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

        condiciones += self._condiciones_de_hora(filtros, "timestamp_evento", parametros)

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
            text(f"SELECT count(*) FROM {TABLA_EVENTOS} WHERE {where}"), parametros
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
                SELECT * FROM {TABLA_EVENTOS}
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
            text(f"SELECT * FROM {TABLA_EVENTOS} WHERE id_evento = :id_evento"),
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
        Se cuenta solo por parámetro: una ejecución del ETL con varias hojas es una única sesión,
        y contar también por nombre partiría el denominador.

        Se calcula sobre las mediciones de la caché, que la detección y el resumen ya han
        cargado: otra consulta solo repetiría el recorrido de la sesión en la base.
        """
        mediciones = self._mediciones_de_sesion(sesion_id)
        total = len(mediciones)
        if not total:
            return []

        filas = []
        for parametro in sorted(_PARAMETROS_RF):
            n_validos = sum(1 for m in mediciones if getattr(m, parametro) is not None)
            filas.append(
                {
                    "parametro": parametro,
                    "n_validos": n_validos,
                    "n_mediciones": total,
                    "pct_validos": round(100.0 * n_validos / total, 1),
                }
            )
        return filas

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
    def _a_medicion(fila, sesion_id: str, sesion_nombre: str | None = None) -> Medicion:
        """Convierte una fila de mediciones en el objeto puro que consume el detector.

        `sesion_id` y `sesion_nombre` llegan aparte porque no viajan en cada fila; si la fila trae
        su propio nombre (sesión con varios), manda el de la fila.
        """
        return Medicion(
            id_medicion=str(fila["id_medicion"]),
            sesion_id=sesion_id,
            sesion_nombre=_texto_compartido(fila.get("sesion_nombre", sesion_nombre)),
            report_index=fila["report_index"],
            timestamp_medicion=fila["timestamp_medicion"],
            tech=_texto_compartido(fila["tech"]),
            net_type=_texto_compartido(fila["net_type"]),
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
            data_state=_texto_compartido(fila["data_state"]),
            call_state=_texto_compartido(fila["call_state"]),
        )
