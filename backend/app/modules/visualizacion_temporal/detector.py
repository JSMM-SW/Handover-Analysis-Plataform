"""
Detector de handovers — algoritmo puro (Capa 3, sin dependencias del proyecto).

Este módulo **no importa nada del proyecto ni hace I/O**: entra una lista de mediciones y sale
una lista de eventos. Es lo que permite probarlo contra datasets sintéticos de verdad conocida
y defender su corrección en la sustentación (`docs/02-arquitectura.md`).

Fundamento teórico: `docs/06-marco-teorico-ho.md` §6.
Validación empírica sobre datos reales: `docs/08-analisis-dataset-real.md` §5.

Qué observa este detector
-------------------------
No vemos la señalización RRC: observamos su **consecuencia**, el cambio de la celda servidora
reportada por el terminal. La detección es, por tanto, una inferencia sobre la serie temporal de
celda servidora, y por eso lleva confirmación, control de huecos y partición por sesión.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# ------------------------------------------------------------------------------------------------
# Constantes del dominio
# ------------------------------------------------------------------------------------------------

#: Muestras consecutivas que debe persistir la nueva celda para aceptar el cambio.
#: Análogo empírico del *time-to-trigger* de 3GPP (docs/06 §4.3).
MUESTRAS_CONFIRMACION_POR_DEFECTO = 2

#: Ventana dentro de la cual una vuelta a la celda anterior se considera efecto ping-pong.
VENTANA_PING_PONG_S_POR_DEFECTO = 10.0

#: Salto temporal por encima del cual un cambio de celda se atribuye a pérdida de captura
#: y no a movilidad observada.
MAX_GAP_S_POR_DEFECTO = 30.0

TIPO_INTRA_FRECUENCIA = "intra_frecuencia"
TIPO_INTER_FRECUENCIA = "inter_frecuencia"
TIPO_INTER_RAT = "inter_rat"
TIPO_DESCONOCIDO = "desconocido"

CONFIANZA_ALTA = "alta"
CONFIANZA_BAJA = "baja"

#: Parámetros de radiofrecuencia para los que se calcula un delta alrededor del evento.
#: RSSNR está incluido a propósito aunque el terminal de referencia nunca lo entregue: otros
#: terminales sí lo miden y el módulo debe admitirlos sin rediseño (decisión D-5).
PARAMETROS_RF = ("rsrp_dbm", "rsrq_db", "rssnr_db", "rscp_dbm", "rssi_dbm")


# ------------------------------------------------------------------------------------------------
# Contratos de entrada y salida
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Medicion:
    """Una medición de la celda servidora, en el formato del contrato (`docs/09`).

    Todos los parámetros RF son opcionales: `None` significa **sin medida válida**. Nunca se usa
    0 ni el centinela 2147483647 de la aplicación, porque 0 dB es un valor físicamente posible
    y confundirlo con "sin dato" falsearía los deltas (decisión D-5).
    """

    id_medicion: str
    sesion_id: str
    timestamp_medicion: datetime

    cid: int | None = None
    node_id: int | None = None
    psc_pci: int | None = None
    lac_tac: int | None = None
    tech: str | None = None
    net_type: str | None = None
    arfcn: int | None = None
    band: int | None = None

    report_index: int | None = None
    sesion_nombre: str | None = None

    rsrp_dbm: int | None = None
    rsrq_db: int | None = None
    rssnr_db: int | None = None
    rscp_dbm: int | None = None
    rssi_dbm: int | None = None

    data_state: str | None = None
    call_state: str | None = None


@dataclass(frozen=True)
class HandoverDetectado:
    """Un evento de handover, con la forma de la tabla `eventos_handover`."""

    sesion_id: str
    sesion_nombre: str | None
    timestamp_evento: datetime
    report_index_evento: int | None

    celda_origen_clave: str
    celda_origen_cid: int | None
    celda_origen_node_id: int | None
    celda_origen_psc_pci: int | None
    celda_origen_arfcn: int | None
    celda_origen_tech: str | None

    celda_destino_clave: str
    celda_destino_cid: int | None
    celda_destino_node_id: int | None
    celda_destino_psc_pci: int | None
    celda_destino_arfcn: int | None
    celda_destino_tech: str | None

    medicion_previa_id: str
    medicion_posterior_id: str

    tipo_evento: str
    ping_pong: bool
    tipo_tecnologia: str | None
    confianza: str
    data_state_evento: str | None

    delta_rsrp_db: float | None
    delta_rsrq_db: float | None
    delta_rssnr_db: float | None
    delta_rscp_db: float | None
    delta_rssi_db: float | None

    duracion_permanencia_s: float
    muestras_confirmacion: int


@dataclass
class DiagnosticoDeteccion:
    """Lo que el detector descartó y por qué. Útil para la memoria de la tesis."""

    mediciones_recibidas: int = 0
    mediciones_sin_identidad: int = 0
    tramos_no_confirmados: int = 0
    cambios_descartados_por_hueco: int = 0
    sesiones_analizadas: int = 0


@dataclass
class ResultadoDeteccion:
    eventos: list[HandoverDetectado] = field(default_factory=list)
    diagnostico: DiagnosticoDeteccion = field(default_factory=DiagnosticoDeteccion)


# ------------------------------------------------------------------------------------------------
# Identidad de celda
# ------------------------------------------------------------------------------------------------


def clave_de_celda(medicion: Medicion) -> str | None:
    """Identidad canónica de la celda servidora de una medición.

    Réplica exacta de la función SQL `vt_celda_clave()` (docs/03 §3) y de la expresión que usa
    el repositorio. Se calcula aquí en lugar de confiar en la columna `celda_clave` para que el
    detector siga siendo puro y probable sin base de datos; `tests/unit/test_detector.py` fija el
    formato para que no se separen.

    - **LTE con `node_id`**: `LTE:<ECI>` con `ECI = node_id * 256 + cid`. En LTE el `cid` es el
      **sector** dentro del eNodeB, no un identificador único: en el dataset real, 9 de sus 26
      valores aparecen bajo varios `node_id` (docs/08 §4).
    - **Resto**: `<tech>:<lac_tac>:<cid>`, porque en GSM/WCDMA no existe `node_id`.

    Devuelve `None` si la medición no tiene `cid`: sin él la celda no es identificable de ninguna
    forma y la medición no puede participar en la detección.
    """
    if medicion.cid is None:
        return None

    if medicion.tech == "LTE" and medicion.node_id is not None:
        return f"LTE:{medicion.node_id * 256 + medicion.cid}"

    tech = medicion.tech or "DESCONOCIDA"
    lac_tac = medicion.lac_tac if medicion.lac_tac is not None else "?"
    return f"{tech}:{lac_tac}:{medicion.cid}"


def confianza_de_celda(medicion: Medicion) -> str:
    """`baja` cuando la identidad es incompleta y hubo que recurrir a la forma de reserva.

    Ocurre en LTE sin `node_id`: no se puede calcular el ECI y dos sectores de nodos distintos
    podrían confundirse.
    """
    if medicion.tech == "LTE" and medicion.node_id is None:
        return CONFIANZA_BAJA
    return CONFIANZA_ALTA


# ------------------------------------------------------------------------------------------------
# Estructura interna: tramos de permanencia
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Tramo:
    """Serie consecutiva de mediciones con la misma celda servidora."""

    clave: str
    mediciones: list[Medicion]

    @property
    def primera(self) -> Medicion:
        return self.mediciones[0]

    @property
    def ultima(self) -> Medicion:
        return self.mediciones[-1]

    @property
    def n_muestras(self) -> int:
        return len(self.mediciones)

    @property
    def duracion_s(self) -> float:
        return (
            self.ultima.timestamp_medicion - self.primera.timestamp_medicion
        ).total_seconds()


def _ordenar(mediciones: list[Medicion]) -> list[Medicion]:
    """Orden total y reproducible: `(timestamp, report_index)`.

    La aplicación muestrea a 1 Hz y puede emitir varias filas en el mismo segundo. Sin
    `report_index` el desempate quedaría al azar y la detección no sería reproducible entre
    ejecuciones (BLQ-08). Cuando no está disponible, el orden de entrada se conserva porque
    `sorted` es estable.
    """
    return sorted(
        mediciones,
        key=lambda m: (
            m.timestamp_medicion,
            m.report_index if m.report_index is not None else -1,
        ),
    )


def _construir_tramos(mediciones: list[Medicion]) -> tuple[list[_Tramo], int]:
    """Agrupa mediciones consecutivas por celda. Devuelve (tramos, mediciones_sin_identidad)."""
    tramos: list[_Tramo] = []
    sin_identidad = 0

    for medicion in mediciones:
        clave = clave_de_celda(medicion)
        if clave is None:
            sin_identidad += 1
            continue

        if tramos and tramos[-1].clave == clave:
            tramos[-1].mediciones.append(medicion)
        else:
            tramos.append(_Tramo(clave=clave, mediciones=[medicion]))

    return tramos, sin_identidad


# ------------------------------------------------------------------------------------------------
# Clasificación y métricas del evento
# ------------------------------------------------------------------------------------------------


def _clasificar(origen: Medicion, destino: Medicion) -> str:
    """intra-frecuencia / inter-frecuencia / inter-RAT (docs/06 §1.2)."""
    if origen.tech != destino.tech:
        return TIPO_INTER_RAT
    if origen.arfcn is None or destino.arfcn is None:
        return TIPO_DESCONOCIDO
    return TIPO_INTRA_FRECUENCIA if origen.arfcn == destino.arfcn else TIPO_INTER_FRECUENCIA


def _tipo_tecnologia(origen: Medicion, destino: Medicion) -> str | None:
    if origen.tech is None and destino.tech is None:
        return None
    if origen.tech == destino.tech:
        return origen.tech
    return f"{origen.tech}->{destino.tech}"


def _delta(previo: Medicion, posterior: Medicion, parametro: str) -> float | None:
    """Variación de un parámetro RF entre las dos mediciones que acotan el evento.

    `None` si falta cualquiera de los dos valores — **nunca 0**: un delta de 0 dB significa "no
    cambió", que es información distinta de "no se pudo medir".
    """
    valor_previo = getattr(previo, parametro)
    valor_posterior = getattr(posterior, parametro)
    if valor_previo is None or valor_posterior is None:
        return None
    return float(valor_posterior - valor_previo)


def _construir_evento(
    tramo_origen: _Tramo,
    tramo_destino: _Tramo,
    muestras_confirmacion: int,
) -> HandoverDetectado:
    """Arma el evento a partir de las dos mediciones que lo acotan.

    Se fecha en la **primera medición con la celda destino**: el primer instante en que el
    traspaso es observable en los datos (docs/06 §6.3).
    """
    previa = tramo_origen.ultima
    posterior = tramo_destino.primera

    confianza = (
        CONFIANZA_BAJA
        if CONFIANZA_BAJA in (confianza_de_celda(previa), confianza_de_celda(posterior))
        else CONFIANZA_ALTA
    )

    deltas = {f"delta_{p.rsplit('_', 1)[0]}_db": _delta(previa, posterior, p) for p in PARAMETROS_RF}

    return HandoverDetectado(
        sesion_id=posterior.sesion_id,
        sesion_nombre=posterior.sesion_nombre,
        timestamp_evento=posterior.timestamp_medicion,
        report_index_evento=posterior.report_index,
        celda_origen_clave=tramo_origen.clave,
        celda_origen_cid=previa.cid,
        celda_origen_node_id=previa.node_id,
        celda_origen_psc_pci=previa.psc_pci,
        celda_origen_arfcn=previa.arfcn,
        celda_origen_tech=previa.tech,
        celda_destino_clave=tramo_destino.clave,
        celda_destino_cid=posterior.cid,
        celda_destino_node_id=posterior.node_id,
        celda_destino_psc_pci=posterior.psc_pci,
        celda_destino_arfcn=posterior.arfcn,
        celda_destino_tech=posterior.tech,
        medicion_previa_id=previa.id_medicion,
        medicion_posterior_id=posterior.id_medicion,
        tipo_evento=_clasificar(previa, posterior),
        ping_pong=False,  # se marca en una segunda pasada, al conocer el evento anterior
        tipo_tecnologia=_tipo_tecnologia(previa, posterior),
        confianza=confianza,
        data_state_evento=posterior.data_state,
        delta_rsrp_db=deltas["delta_rsrp_db"],
        delta_rsrq_db=deltas["delta_rsrq_db"],
        delta_rssnr_db=deltas["delta_rssnr_db"],
        delta_rscp_db=deltas["delta_rscp_db"],
        delta_rssi_db=deltas["delta_rssi_db"],
        duracion_permanencia_s=tramo_origen.duracion_s,
        muestras_confirmacion=muestras_confirmacion,
    )


def _marcar_ping_pong(
    eventos: list[HandoverDetectado], ventana_s: float
) -> list[HandoverDetectado]:
    """Marca A→B→A: el destino de un evento coincide con el origen del anterior (docs/06 §5.1)."""
    marcados: list[HandoverDetectado] = []

    for indice, evento in enumerate(eventos):
        es_ping_pong = False
        if indice > 0:
            anterior = eventos[indice - 1]
            transcurrido = (
                evento.timestamp_evento - anterior.timestamp_evento
            ).total_seconds()
            es_ping_pong = (
                evento.celda_destino_clave == anterior.celda_origen_clave
                and transcurrido <= ventana_s
            )

        marcados.append(
            evento if not es_ping_pong else _con_ping_pong(evento)
        )

    return marcados


def _con_ping_pong(evento: HandoverDetectado) -> HandoverDetectado:
    from dataclasses import replace

    return replace(evento, ping_pong=True)


# ------------------------------------------------------------------------------------------------
# Algoritmo principal
# ------------------------------------------------------------------------------------------------


def detectar_handovers_detallado(
    mediciones: list[Medicion],
    muestras_confirmacion: int = MUESTRAS_CONFIRMACION_POR_DEFECTO,
    ventana_ping_pong_s: float = VENTANA_PING_PONG_S_POR_DEFECTO,
    max_gap_s: float = MAX_GAP_S_POR_DEFECTO,
) -> ResultadoDeteccion:
    """Detecta los handovers y devuelve además el diagnóstico de lo descartado.

    Un cambio de celda se registra como handover cuando se cumple **todo** (docs/06 §6.3):

    1. Dos mediciones consecutivas tienen identidad de celda distinta.
    2. La nueva celda **persiste** al menos `muestras_confirmacion` mediciones. Filtra las
       lecturas espurias de la aplicación de medición.
    3. Ambas pertenecen a la **misma sesión**. Un cambio entre el final de un recorrido y el
       principio de otro no es un traspaso.
    4. El salto temporal entre ambas no supera `max_gap_s`. Un hueco largo indica pérdida de
       captura, no movilidad observada.
    """
    if muestras_confirmacion < 1:
        raise ValueError("muestras_confirmacion debe ser >= 1")
    if max_gap_s <= 0:
        raise ValueError("max_gap_s debe ser > 0")

    diagnostico = DiagnosticoDeteccion(mediciones_recibidas=len(mediciones))
    eventos: list[HandoverDetectado] = []

    if not mediciones:
        return ResultadoDeteccion(eventos=eventos, diagnostico=diagnostico)

    # Partición por sesión: nunca se compara una medición con la de otro recorrido.
    por_sesion: dict[str, list[Medicion]] = {}
    for medicion in mediciones:
        por_sesion.setdefault(medicion.sesion_id, []).append(medicion)

    diagnostico.sesiones_analizadas = len(por_sesion)

    for sesion_id in sorted(por_sesion):
        tramos, sin_identidad = _construir_tramos(_ordenar(por_sesion[sesion_id]))
        diagnostico.mediciones_sin_identidad += sin_identidad

        eventos_sesion: list[HandoverDetectado] = []
        tramo_confirmado: _Tramo | None = None

        for tramo in tramos:
            # Un tramo demasiado corto es ruido de medición: no cambia la celda vigente.
            if tramo.n_muestras < muestras_confirmacion:
                if tramo_confirmado is not None:
                    diagnostico.tramos_no_confirmados += 1
                continue

            if tramo_confirmado is None:
                tramo_confirmado = tramo
                continue

            if tramo.clave == tramo_confirmado.clave:
                # Puede ocurrir si entre medias hubo tramos no confirmados: seguimos en la misma
                # celda, así que no hay evento, pero sí hay que extender la permanencia.
                tramo_confirmado = _Tramo(
                    clave=tramo_confirmado.clave,
                    mediciones=tramo_confirmado.mediciones + tramo.mediciones,
                )
                continue

            salto_s = (
                tramo.primera.timestamp_medicion
                - tramo_confirmado.ultima.timestamp_medicion
            ).total_seconds()

            if salto_s > max_gap_s:
                # Hubo pérdida de captura: cambiamos de celda vigente sin registrar evento.
                diagnostico.cambios_descartados_por_hueco += 1
                tramo_confirmado = tramo
                continue

            eventos_sesion.append(
                _construir_evento(tramo_confirmado, tramo, muestras_confirmacion)
            )
            tramo_confirmado = tramo

        eventos.extend(_marcar_ping_pong(eventos_sesion, ventana_ping_pong_s))

    eventos.sort(key=lambda e: (e.sesion_id, e.timestamp_evento))
    return ResultadoDeteccion(eventos=eventos, diagnostico=diagnostico)


def detectar_handovers(
    mediciones: list[Medicion],
    muestras_confirmacion: int = MUESTRAS_CONFIRMACION_POR_DEFECTO,
    ventana_ping_pong_s: float = VENTANA_PING_PONG_S_POR_DEFECTO,
    max_gap_s: float = MAX_GAP_S_POR_DEFECTO,
) -> list[HandoverDetectado]:
    """Igual que `detectar_handovers_detallado` pero devolviendo solo los eventos."""
    return detectar_handovers_detallado(
        mediciones,
        muestras_confirmacion=muestras_confirmacion,
        ventana_ping_pong_s=ventana_ping_pong_s,
        max_gap_s=max_gap_s,
    ).eventos
