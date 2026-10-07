"""
Dataset sintético de referencia del Módulo 2 — *verdad de referencia* del detector.

Por qué existe
--------------
El detector de handovers (`detector.py`) es una función pura y debe poder probarse sin base de
datos y sin depender de que el Módulo 1 esté terminado. Este módulo construye un recorrido
sintético **con handovers de verdad conocida**, declarados a mano en `EVENTOS_ESPERADOS`.

Regla anti-circularidad
-----------------------
Los eventos esperados **se declaran explícitamente**, no se calculan con el algoritmo del
detector. Si se derivasen del propio algoritmo, la prueba sería una tautología. Aquí solo se
afirma "en el segundo 90 la celda servidora pasa de A a B", que es un hecho de construcción del
dataset, y es el detector quien debe redescubrirlo.

Uso
---
Fixture **en memoria** de las pruebas unitarias de `detector.py` y de `services.py`. No se carga
en la base de datos: la aplicación trabaja solo con las sesiones reales del Módulo 1.

Convenciones
------------
- Los timestamps se generan en **UTC**, como los persiste el Módulo 1.
- `report_index` reproduce la columna `report` del export real: contador secuencial sin huecos
  que da orden total incluso con timestamps repetidos.
- Los parámetros RF sin medida se representan con `None` (→ `NULL` en SQL), nunca con 0 ni con el
  centinela `2147483647`: un SINR de 0 dB es un valor válido y confundirlo con "sin dato"
  corrompería medias y gráficas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------------------------
# Identidad de la sesión
# --------------------------------------------------------------------------------------------

SESION_ID = "11111111-1111-4111-8111-111111111111"
SESION_NOMBRE = "Session_S1_20260701_080000"

# 2026-07-01 08:00:00 en America/Guayaquil (UTC-5) = 13:00:00 UTC
INICIO_UTC = datetime(2026, 7, 1, 13, 0, 0, tzinfo=timezone.utc)

ARCHIVO_ORIGEN = "dataset_sintetico_M2.xlsx"


# --------------------------------------------------------------------------------------------
# Celdas del recorrido
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Celda:
    """Una celda servidora del recorrido sintético.

    `clave` es la identidad canónica que debe calcular el detector (ver `docs/06` §3.1):
    en LTE `LTE:<node_id*256+cid>`; en el resto `<tech>:<lac_tac>:<cid>`.
    """

    etiqueta: str
    tech: str
    cid: int
    node_id: int | None
    psc_pci: int | None
    lac_tac: int
    arfcn: int | None
    band: int | None
    rsrp_base: int | None
    rsrq_base: int | None
    rscp_base: int | None = None
    rssi_base: int | None = None

    @property
    def clave(self) -> str:
        if self.tech == "LTE" and self.node_id is not None:
            return f"LTE:{self.node_id * 256 + self.cid}"
        return f"{self.tech}:{self.lac_tac}:{self.cid}"

    @property
    def confianza(self) -> str:
        """`baja` cuando falta el identificador de nodo y la celda no es plenamente identificable."""
        return "baja" if (self.tech == "LTE" and self.node_id is None) else "alta"


# Valores tomados del dataset real (docs/08 §2.3): node_id de 5 dígitos, cid de sector 70-210,
# EARFCN 850 -> banda 2 (1900 MHz) y EARFCN 9435 -> banda 28 (700 MHz).
CELDA_A = Celda("A", "LTE", 198, 28178, 461, 35191, 850, 1900, rsrp_base=-82, rsrq_base=-9)
CELDA_B = Celda("B", "LTE", 197, 28868, 460, 35191, 850, 1900, rsrp_base=-86, rsrq_base=-10)
CELDA_C = Celda("C", "LTE", 196, 28087, 375, 35191, 9435, 700, rsrp_base=-90, rsrq_base=-12)
CELDA_D = Celda("D", "LTE", 210, 28269, 44, 35191, 850, 1900, rsrp_base=-88, rsrq_base=-11)
CELDA_E = Celda("E", "LTE", 203, 28433, 283, 35191, 850, 1900, rsrp_base=-84, rsrq_base=-9)
CELDA_F = Celda("F", "LTE", 192, 28895, 237, 33185, 850, 1900, rsrp_base=-92, rsrq_base=-14)

# Inter-RAT: WCDMA. En WCDMA no hay node_id y la señal es RSCP, no RSRP.
CELDA_W = Celda(
    "W", "WCDMA", 30405, None, 239, 13163, None, None,
    rsrp_base=None, rsrq_base=None, rscp_base=-101,
)

# Celda LTE con `node_id` ausente: reproduce el caso de identidad incompleta -> confianza baja.
CELDA_N = Celda("N", "LTE", 191, None, 151, 33184, 850, 1900, rsrp_base=-95, rsrq_base=-16)


# --------------------------------------------------------------------------------------------
# Estructura temporal del recorrido
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Tramo:
    """Permanencia continua en una celda, en segundos desde el inicio de la sesión."""

    celda: Celda
    inicio_s: int
    fin_s: int  # exclusivo

    @property
    def duracion_s(self) -> int:
        return self.fin_s - self.inicio_s


# Hueco deliberado de captura: no se emite ninguna medición en este intervalo.
# Sirve para probar que un salto temporal largo NO se interpreta como handover.
HUECO_INICIO_S = 432
HUECO_FIN_S = 462  # exclusivo -> 30 s sin datos

TRAMOS: list[Tramo] = [
    Tramo(CELDA_A, 0, 90),      # 90 s
    Tramo(CELDA_B, 90, 180),    # HO1  A->B  intra-frecuencia (850 -> 850)
    Tramo(CELDA_C, 180, 270),   # HO2  B->C  inter-frecuencia (850 -> 9435)
    Tramo(CELDA_D, 270, 360),   # HO3  C->D  inter-frecuencia (9435 -> 850)
    Tramo(CELDA_E, 360, 414),   # HO4  D->E  intra-frecuencia
    Tramo(CELDA_F, 414, 420),   # HO5  E->F  intra-frecuencia
    Tramo(CELDA_E, 420, 432),   # HO6  F->E  intra-frecuencia + PING-PONG (destino = origen de HO5)
    Tramo(CELDA_E, 462, 522),   # tras el hueco, MISMA celda -> NO es handover
    Tramo(CELDA_W, 522, 582),   # HO7  E->W  INTER-RAT (LTE -> WCDMA)
    Tramo(CELDA_N, 582, 630),   # HO8  W->N  INTER-RAT (WCDMA -> LTE), confianza BAJA
]


@dataclass(frozen=True)
class EventoEsperado:
    """Un handover que el detector **debe** encontrar. Declarado a mano, no calculado."""

    segundo: int
    origen: str          # etiqueta de celda
    destino: str
    tipo_evento: str     # intra_frecuencia | inter_frecuencia | inter_rat
    ping_pong: bool
    confianza: str


EVENTOS_ESPERADOS: list[EventoEsperado] = [
    EventoEsperado(90,  "A", "B", "intra_frecuencia", False, "alta"),
    EventoEsperado(180, "B", "C", "inter_frecuencia", False, "alta"),
    EventoEsperado(270, "C", "D", "inter_frecuencia", False, "alta"),
    EventoEsperado(360, "D", "E", "intra_frecuencia", False, "alta"),
    EventoEsperado(414, "E", "F", "intra_frecuencia", False, "alta"),
    EventoEsperado(420, "F", "E", "intra_frecuencia", True,  "alta"),
    EventoEsperado(522, "E", "W", "inter_rat",        False, "alta"),
    EventoEsperado(582, "W", "N", "inter_rat",        False, "baja"),
]

TOTAL_HANDOVERS_ESPERADOS = len(EVENTOS_ESPERADOS)   # 8
TOTAL_MEDICIONES_ESPERADAS = 600
CELDAS_DISTINTAS_ESPERADAS = 8                        # A, B, C, D, E, F, W, N

# Parámetros de detección con los que la verdad de referencia es válida.
MUESTRAS_CONFIRMACION = 2
VENTANA_PING_PONG_S = 10
MAX_GAP_S = 15   # < 30 s del hueco, por eso el hueco no genera evento


# --------------------------------------------------------------------------------------------
# Generación de las mediciones
# --------------------------------------------------------------------------------------------


def _degradacion(offset: int, duracion: int) -> float:
    """Fracción de degradación dentro de una permanencia: 0 al entrar, 1 al salir.

    Crece de forma cuadrática para que la caída se concentre al final del tramo, que es el
    comportamiento que motiva el handover (docs/06 §4.3).
    """
    if duracion <= 1:
        return 0.0
    return (offset / (duracion - 1)) ** 2


def _rf_de_la_muestra(celda: Celda, offset: int, duracion: int) -> dict:
    """Calcula los parámetros RF de una muestra, con degradación hacia el final del tramo."""
    f = _degradacion(offset, duracion)

    rsrp = rsrq = rscp = rssi = None
    if celda.rsrp_base is not None:
        rsrp = int(round(celda.rsrp_base - 18 * f))
        rsrp = max(-140, min(-44, rsrp))
    if celda.rsrq_base is not None:
        rsrq = int(round(celda.rsrq_base - 6 * f))
        rsrq = max(-20, min(-3, rsrq))
    if celda.rscp_base is not None:
        rscp = int(round(celda.rscp_base - 12 * f))
    if celda.rssi_base is not None:
        rssi = int(round(celda.rssi_base - 12 * f))

    return {"rsrp_dbm": rsrp, "rsrq_db": rsrq, "rscp_dbm": rscp, "rssi_dbm": rssi}


def _rssnr_de_la_muestra(segundo: int, rsrp: int | None) -> int | None:
    """RSSNR/SINR: disponible solo en la primera mitad del recorrido.

    Reproduce a propósito las dos situaciones que el módulo debe saber pintar:
    un tramo **con** medida de SINR y otro **sin** ella. En el dataset real de referencia
    (`docs/08` §2.4) la aplicación nunca lo entrega, pero otros terminales sí lo hacen, así que
    el parámetro es de primera clase en toda la pila y su ausencia se representa con `NULL`.
    """
    if segundo >= 270 or rsrp is None:
        return None
    # Relación aproximada y monótona con RSRP, acotada al rango físico -20..+30 dB.
    return max(-20, min(30, int(round((rsrp + 120) / 2.2))))


def generar_mediciones() -> list[dict]:
    """Devuelve las mediciones del recorrido sintético, ordenadas y con `report_index` continuo."""
    mediciones: list[dict] = []
    report_index = 0

    for tramo in TRAMOS:
        for offset in range(tramo.duracion_s):
            segundo = tramo.inicio_s + offset
            celda = tramo.celda
            rf = _rf_de_la_muestra(celda, offset, tramo.duracion_s)

            mediciones.append(
                {
                    "report_index": report_index,
                    "sesion_id": SESION_ID,
                    "sesion_nombre": SESION_NOMBRE,
                    "timestamp_medicion": INICIO_UTC + timedelta(seconds=segundo),
                    "segundo_relativo": segundo,
                    "tech": celda.tech,
                    "net_type": "LTE" if celda.tech == "LTE" else "UMTS",
                    "cid": celda.cid,
                    "node_id": celda.node_id,
                    "psc_pci": celda.psc_pci,
                    "lac_tac": celda.lac_tac,
                    "arfcn": celda.arfcn,
                    "band": celda.band,
                    "celda_clave": celda.clave,
                    "rssnr_db": _rssnr_de_la_muestra(segundo, rf["rsrp_dbm"]),
                    "data_state": "CONNECTED" if celda.tech == "LTE" else "DISCONNECTED",
                    "call_state": "IDLE",
                    "gps_fix": False,
                    "latitud": None,
                    "longitud": None,
                    "archivo_origen": ARCHIVO_ORIGEN,
                    **rf,
                }
            )
            report_index += 1

    return mediciones


def celda_por_etiqueta(etiqueta: str) -> Celda:
    """Traduce la etiqueta usada en `EVENTOS_ESPERADOS` a su objeto `Celda`."""
    for tramo in TRAMOS:
        if tramo.celda.etiqueta == etiqueta:
            return tramo.celda
    raise KeyError(f"No existe la celda sintética {etiqueta!r}")


def verificar_coherencia() -> None:
    """Comprueba que el dataset construido cumple lo que declara. Se ejecuta en las pruebas.

    No usa el algoritmo del detector: solo contrasta la construcción (fronteras de tramo)
    contra la verdad declarada a mano.
    """
    mediciones = generar_mediciones()

    assert len(mediciones) == TOTAL_MEDICIONES_ESPERADAS, (
        f"El recorrido produce {len(mediciones)} mediciones, se esperaban "
        f"{TOTAL_MEDICIONES_ESPERADAS}"
    )

    # `report_index` continuo y sin huecos, aunque haya un hueco temporal.
    assert [m["report_index"] for m in mediciones] == list(range(len(mediciones)))

    # Orden temporal estrictamente creciente.
    tiempos = [m["timestamp_medicion"] for m in mediciones]
    assert all(a < b for a, b in zip(tiempos, tiempos[1:])), "Los timestamps no son crecientes"

    # El hueco existe y dura lo declarado.
    segundos = {m["segundo_relativo"] for m in mediciones}
    hueco = set(range(HUECO_INICIO_S, HUECO_FIN_S))
    assert not (segundos & hueco), "El hueco temporal contiene mediciones"
    assert HUECO_FIN_S - HUECO_INICIO_S == 30

    # Cada evento declarado coincide con una frontera real de cambio de celda.
    por_segundo = {m["segundo_relativo"]: m for m in mediciones}
    for evento in EVENTOS_ESPERADOS:
        actual = por_segundo[evento.segundo]
        anterior = por_segundo[evento.segundo - 1]
        origen, destino = celda_por_etiqueta(evento.origen), celda_por_etiqueta(evento.destino)

        assert anterior["celda_clave"] == origen.clave, (
            f"En el segundo {evento.segundo - 1} se esperaba la celda {evento.origen}"
        )
        assert actual["celda_clave"] == destino.clave, (
            f"En el segundo {evento.segundo} se esperaba la celda {evento.destino}"
        )
        assert destino.confianza == evento.confianza

    # Ningún cambio de celda no declarado.
    cambios = [
        m["segundo_relativo"]
        for anterior, m in zip(mediciones, mediciones[1:])
        if m["celda_clave"] != anterior["celda_clave"]
    ]
    declarados = sorted(e.segundo for e in EVENTOS_ESPERADOS)
    assert sorted(cambios) == declarados, (
        f"Cambios de celda en {sorted(cambios)}, declarados {declarados}"
    )

    # El cambio a través del hueco no debe existir (misma celda a ambos lados).
    assert por_segundo[HUECO_INICIO_S - 1]["celda_clave"] == por_segundo[HUECO_FIN_S]["celda_clave"]

    # Cobertura de RSSNR: parcial a propósito.
    con_rssnr = sum(1 for m in mediciones if m["rssnr_db"] is not None)
    assert 0 < con_rssnr < len(mediciones), "RSSNR debe estar parcialmente disponible"

    assert len({m["celda_clave"] for m in mediciones}) == CELDAS_DISTINTAS_ESPERADAS
