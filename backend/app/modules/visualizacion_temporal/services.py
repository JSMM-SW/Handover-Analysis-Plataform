"""
Servicios del Módulo 2 — Capa 3, orquestación.

Coordina repositorio y detector, pero **no ejecuta SQL ni conoce FastAPI**: recibe un repositorio
ya construido y lanza excepciones de dominio, que el router traduce a códigos HTTP
(`docs/02-arquitectura.md`).
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from datetime import time as dt_time

from app.modules.visualizacion_temporal.detector import (
    HandoverDetectado,
    detectar_handovers_detallado,
)
from app.modules.visualizacion_temporal.exceptions import (
    HandoverNoEncontrado,
    SesionNoEncontrada,
    SesionSinMediciones,
)
from app.modules.visualizacion_temporal.lttb import (
    indice_de_mejor_cobertura,
    seleccionar_indices_lttb,
)
from app.modules.visualizacion_temporal.schemas import (
    ETIQUETAS_RF,
    PARAMETROS_RF,
    BinIntervalo,
    CeldaResumen,
    CeldaRepetida,
    CeldasRepetidasOut,
    CoberturaParametro,
    DiagnosticoDeteccion,
    DiaDisponible,
    DisponibilidadOut,
    EstadisticasParametro,
    EventoHandover,
    FranjaHoraria,
    PaginaHandovers,
    ParametrosDeteccion,
    ResumenDeteccion,
    ResumenOut,
    SeriesOut,
    SesionOut,
    TramoCelda,
    TramosCeldaOut,
    VentanaHandoverOut,
)

logger = logging.getLogger(__name__)


def ejecutar_deteccion(
    sesion_id: str,
    parametros: ParametrosDeteccion,
    repository,
    desde: datetime | None = None,
    hasta: datetime | None = None,
) -> ResumenDeteccion:
    """Detecta los handovers de una sesión y los persiste (HU-C2-001).

    Flujo: valida la sesión → lee mediciones → detecta → borra previos → guarda → resume.

    La detección es **idempotente**: con `recalcular=True` (por defecto) se borran los eventos
    previos de la sesión antes de insertar, de modo que reejecutarla con otros parámetros deja
    un estado limpio en lugar de acumular duplicados.
    """
    inicio = time.perf_counter()

    if not repository.existe_sesion(sesion_id):
        raise SesionNoEncontrada(sesion_id)

    mediciones = repository.obtener_mediciones(sesion_id, desde=desde, hasta=hasta)
    if not mediciones:
        raise SesionSinMediciones(sesion_id)

    resultado = detectar_handovers_detallado(
        mediciones,
        muestras_confirmacion=parametros.muestras_confirmacion,
        ventana_ping_pong_s=parametros.ventana_ping_pong_s,
        max_gap_s=parametros.max_gap_s,
    )

    # Todas las mediciones sin celda identificable: la sesión no sirve para el análisis temporal.
    if resultado.diagnostico.mediciones_sin_identidad == len(mediciones):
        raise SesionSinMediciones(sesion_id)

    if resultado.diagnostico.cambios_descartados_por_hueco:
        logger.info(
            "Sesión %s: %d cambios de celda descartados por hueco de captura (> %.1f s).",
            sesion_id,
            resultado.diagnostico.cambios_descartados_por_hueco,
            parametros.max_gap_s,
        )

    parametros_usados = {
        "muestras_confirmacion": parametros.muestras_confirmacion,
        "ventana_ping_pong_s": parametros.ventana_ping_pong_s,
        "max_gap_s": parametros.max_gap_s,
    }

    if parametros.recalcular:
        borrados = repository.borrar_handovers_de_sesion(sesion_id)
        if borrados:
            logger.info("Sesión %s: %d eventos previos borrados antes de recalcular.", sesion_id, borrados)

    repository.guardar_handovers(resultado.eventos, parametros_usados)

    resumen = _construir_resumen(
        sesion_id=sesion_id,
        mediciones=mediciones,
        resultado=resultado,
        parametros=parametros,
        cobertura=repository.obtener_cobertura_parametros(sesion_id),
    )
    resumen.duracion_ms = int((time.perf_counter() - inicio) * 1000)
    return resumen


def _construir_resumen(
    sesion_id: str,
    mediciones: list,
    resultado,
    parametros: ParametrosDeteccion,
    cobertura: list[dict],
) -> ResumenDeteccion:
    """Agrega los totales que exige el criterio 3 de HU-C2-001."""
    eventos = resultado.eventos

    por_tipo: dict[str, int] = {}
    por_tecnologia: dict[str, int] = {}
    for evento in eventos:
        por_tipo[evento.tipo_evento] = por_tipo.get(evento.tipo_evento, 0) + 1
        clave_tec = evento.tipo_tecnologia or "desconocida"
        por_tecnologia[clave_tec] = por_tecnologia.get(clave_tec, 0) + 1

    # Radiobases distintas vistas en la sesión, no solo las implicadas en un handover.
    from app.modules.visualizacion_temporal.detector import clave_de_celda

    claves = {clave_de_celda(m) for m in mediciones}
    claves.discard(None)

    tiempos = [m.timestamp_medicion for m in mediciones]

    return ResumenDeteccion(
        sesion_id=sesion_id,
        sesion_nombre=next((m.sesion_nombre for m in mediciones if m.sesion_nombre), None),
        total_handovers=len(eventos),
        por_tipo=por_tipo,
        por_tecnologia=por_tecnologia,
        total_ping_pong=sum(1 for e in eventos if e.ping_pong),
        total_confianza_baja=sum(1 for e in eventos if e.confianza == "baja"),
        radiobases_involucradas=len(claves),
        ventana_inicio=min(tiempos) if tiempos else None,
        ventana_fin=max(tiempos) if tiempos else None,
        cobertura_parametros=_construir_cobertura(cobertura, mediciones),
        diagnostico=DiagnosticoDeteccion(
            mediciones_recibidas=resultado.diagnostico.mediciones_recibidas,
            mediciones_sin_identidad=resultado.diagnostico.mediciones_sin_identidad,
            tramos_no_confirmados=resultado.diagnostico.tramos_no_confirmados,
            cambios_descartados_por_hueco=resultado.diagnostico.cambios_descartados_por_hueco,
            sesiones_analizadas=resultado.diagnostico.sesiones_analizadas,
        ),
        parametros_usados=parametros,
    )


def _construir_cobertura(
    cobertura_bd: list[dict], mediciones: list
) -> list[CoberturaParametro]:
    """Cobertura de cada parámetro RF, con `disponible=False` cuando no hay ni una medida.

    Se prefieren las cifras de cobertura del repositorio (cubren toda la sesión). Si
    no están disponibles —por ejemplo con un repositorio en memoria en pruebas— se calculan
    sobre las mediciones ya leídas.

    Siempre se devuelven **los cinco parámetros**, incluidos los que no tienen ni un valor: es
    precisamente lo que permite a la interfaz decir "SINR: sin datos válidos" en lugar de no
    mostrar nada (decisión D-5).
    """
    # Se acumulan las filas por parámetro en lugar de quedarse con la última: si el repositorio
    # devolviera más de una fila por parámetro (p. ej. una ejecución del ETL con varias hojas),
    # quedarse con una sola daría un denominador parcial y un porcentaje falso.
    por_parametro: dict[str, dict] = {}
    for fila in cobertura_bd:
        acumulado = por_parametro.setdefault(
            fila["parametro"], {"n_validos": 0, "n_mediciones": 0}
        )
        acumulado["n_validos"] += int(fila["n_validos"])
        acumulado["n_mediciones"] += int(fila["n_mediciones"])

    total_mediciones = len(mediciones)

    resultado: list[CoberturaParametro] = []
    for parametro in PARAMETROS_RF:
        fila = por_parametro.get(parametro)
        if fila is not None:
            n_validos = fila["n_validos"]
            n_mediciones = fila["n_mediciones"]
        else:
            n_validos = sum(1 for m in mediciones if getattr(m, parametro, None) is not None)
            n_mediciones = total_mediciones

        pct = round(100.0 * n_validos / n_mediciones, 1) if n_mediciones else 0.0
        resultado.append(
            CoberturaParametro(
                parametro=parametro,
                etiqueta=ETIQUETAS_RF[parametro],
                n_validos=n_validos,
                n_mediciones=n_mediciones,
                pct_validos=pct,
                disponible=n_validos > 0,
            )
        )

    return resultado


def a_schema_evento(evento: HandoverDetectado, id_evento: str | None = None) -> EventoHandover:
    """Traduce un evento del detector al contrato de salida de la API."""
    return EventoHandover(
        id_evento=id_evento,
        sesion_id=evento.sesion_id,
        sesion_nombre=evento.sesion_nombre,
        timestamp_evento=evento.timestamp_evento,
        report_index_evento=evento.report_index_evento,
        celda_origen=CeldaResumen(
            clave=evento.celda_origen_clave,
            cid=evento.celda_origen_cid,
            node_id=evento.celda_origen_node_id,
            psc_pci=evento.celda_origen_psc_pci,
            arfcn=evento.celda_origen_arfcn,
            tech=evento.celda_origen_tech,
        ),
        celda_destino=CeldaResumen(
            clave=evento.celda_destino_clave,
            cid=evento.celda_destino_cid,
            node_id=evento.celda_destino_node_id,
            psc_pci=evento.celda_destino_psc_pci,
            arfcn=evento.celda_destino_arfcn,
            tech=evento.celda_destino_tech,
        ),
        medicion_previa_id=evento.medicion_previa_id,
        medicion_posterior_id=evento.medicion_posterior_id,
        tipo_evento=evento.tipo_evento,
        ping_pong=evento.ping_pong,
        tipo_tecnologia=evento.tipo_tecnologia,
        confianza=evento.confianza,
        data_state_evento=evento.data_state_evento,
        delta_rsrp_db=evento.delta_rsrp_db,
        delta_rsrq_db=evento.delta_rsrq_db,
        delta_rssnr_db=evento.delta_rssnr_db,
        delta_rscp_db=evento.delta_rscp_db,
        delta_rssi_db=evento.delta_rssi_db,
        duracion_permanencia_s=evento.duracion_permanencia_s,
        muestras_confirmacion=evento.muestras_confirmacion,
    )


# ================================================================================================
# Fase 3 — servicios de lectura para las visualizaciones
# ================================================================================================

#: Salto temporal por encima del cual la gráfica debe **cortar la línea** en vez de unir dos
#: puntos entre los que no hubo captura.
MAX_GAP_GRAFICA_S = 30.0


def listar_sesiones(repository) -> list[SesionOut]:
    """Sesiones disponibles para el selector del header (HU-C2-006)."""
    return [
        SesionOut(
            sesion_id=str(fila["sesion_id"]),
            sesion_nombre=fila.get("sesion_nombre"),
            inicio=fila.get("inicio"),
            fin=fila.get("fin"),
            n_mediciones=int(fila.get("n_mediciones") or 0),
            n_celdas=int(fila.get("n_celdas") or 0),
            tecnologias=sorted(fila.get("tecnologias") or []),
            n_handovers=int(fila.get("n_handovers") or 0),
        )
        for fila in repository.listar_sesiones()
    ]


def _exigir_sesion(sesion_id: str, repository) -> None:
    if not repository.existe_sesion(sesion_id):
        raise SesionNoEncontrada(sesion_id)


def _sesiones_de(filtros) -> list[str]:
    """Sesiones que abarca un filtro: la lista si la hay, o la sesión única."""
    return list(getattr(filtros, "sesion_ids", None) or [filtros.sesion_id])


def _exigir_sesiones(filtros, repository) -> None:
    """Todas las sesiones pedidas deben existir: analizar «las que haya» ocultaría un error."""
    for sesion_id in _sesiones_de(filtros):
        _exigir_sesion(sesion_id, repository)


def _nombre(parametro) -> str:
    return parametro.value if hasattr(parametro, "value") else str(parametro)


def obtener_series(
    filtros,
    parametros: list,
    max_puntos: int = 3000,
    max_gap_s: float = MAX_GAP_GRAFICA_S,
    repository=None,
) -> SeriesOut:
    """Series temporales de parámetros RF en formato columnar (HU-C2-004).

    Tres cosas que hace y conviene entender:

    1. **Corta la línea en los huecos de captura.** Si entre dos mediciones consecutivas pasan más
       de `max_gap_s`, se inserta un punto nulo para que la gráfica no dibuje un segmento recto
       sobre un intervalo en el que no se midió nada.
    2. **Aplica downsampling LTTB** cuando la serie excede `max_puntos`, conservando la forma. Los
       índices se eligen **una sola vez**, sobre el parámetro con mejor cobertura, y se aplican a
       todas las series para que los arrays queden alineados con el eje de tiempos.
    3. **Informa de la cobertura** de cada parámetro pedido, para que la interfaz pueda mostrar
       "sin datos válidos" en lugar de una gráfica vacía sin explicación (decisión D-5).
    """
    _exigir_sesiones(filtros, repository)

    mediciones = repository.obtener_mediciones_filtradas(filtros)
    nombres = [_nombre(p) for p in parametros] or list(PARAMETROS_RF)

    if not mediciones:
        return SeriesOut(
            t=[],
            series={nombre: [] for nombre in nombres},
            downsampled=False,
            puntos_originales=0,
            puntos_devueltos=0,
            cobertura=_construir_cobertura([], []),
        )

    segmentos = _partir_en_segmentos(mediciones, max_gap_s)
    seleccion = _seleccionar_por_segmentos(segmentos, nombres, max_puntos)

    t: list = []
    series: dict[str, list] = {nombre: [] for nombre in nombres}

    for indice_segmento, indices in enumerate(seleccion):
        if indice_segmento > 0:
            # Punto nulo que rompe la línea entre dos tramos de captura.
            t.append(None)
            for nombre in nombres:
                series[nombre].append(None)

        for medicion in indices:
            t.append(medicion.timestamp_medicion)
            for nombre in nombres:
                valor = getattr(medicion, nombre, None)
                series[nombre].append(float(valor) if valor is not None else None)

    devueltos = sum(len(indices) for indices in seleccion)

    return SeriesOut(
        t=t,
        series=series,
        downsampled=devueltos < len(mediciones),
        puntos_originales=len(mediciones),
        puntos_devueltos=devueltos,
        cobertura=[
            c
            for c in _construir_cobertura([], mediciones)
            if c.parametro in nombres
        ],
    )


def _partir_en_segmentos(mediciones: list, max_gap_s: float) -> list[list]:
    """Corta la serie allí donde hubo pérdida de captura o se pasa de una sesión a otra.

    Con varias sesiones a la vez, unir el último punto de un recorrido con el primero del
    siguiente dibujaría una transición que nunca ocurrió.
    """
    segmentos: list[list] = [[mediciones[0]]]

    for anterior, actual in zip(mediciones, mediciones[1:]):
        salto = (actual.timestamp_medicion - anterior.timestamp_medicion).total_seconds()
        otra_sesion = getattr(actual, "sesion_id", None) != getattr(anterior, "sesion_id", None)
        if salto > max_gap_s or otra_sesion:
            segmentos.append([actual])
        else:
            segmentos[-1].append(actual)

    return segmentos


def _seleccionar_por_segmentos(
    segmentos: list[list], nombres: list[str], max_puntos: int
) -> list[list]:
    """Reparte el presupuesto de puntos entre los segmentos y aplica LTTB a cada uno."""
    total = sum(len(s) for s in segmentos)
    if total <= max_puntos:
        return segmentos

    seleccion: list[list] = []
    for segmento in segmentos:
        # Presupuesto proporcional al tamaño del segmento, con un mínimo de 2 (sus extremos).
        cupo = max(2, round(max_puntos * len(segmento) / total))
        if len(segmento) <= cupo:
            seleccion.append(segmento)
            continue

        xs = [m.timestamp_medicion.timestamp() for m in segmento]
        series_segmento = {
            nombre: [getattr(m, nombre, None) for m in segmento] for nombre in nombres
        }
        referencia = indice_de_mejor_cobertura(series_segmento)
        ys = series_segmento[referencia] if referencia else [None] * len(segmento)

        indices = seleccionar_indices_lttb(xs, ys, cupo)
        seleccion.append([segmento[i] for i in indices])

    return seleccion


def etiqueta_pci_psc(tech: str | None, psc_pci: int | None, cid: int | None) -> str:
    """Rótulo físico de una celda: «PCI n» en LTE, «PSC n» en WCDMA.

    - GSM no tiene PCI ni PSC (su equivalente, el BSIC, no viene en los datos): se rotula con su
      CID, «GSM CID n».
    - Una celda LTE o WCDMA que no ha informado **nunca** de su PCI/PSC se rotula «Sin PCI» o
      «Sin PSC». No se recurre al CID para no mezclar dos clases de número en el mismo eje.
    """
    if psc_pci is not None and tech == "WCDMA":
        return f"PSC {psc_pci}"
    if psc_pci is not None:
        return f"PCI {psc_pci}"
    if tech == "LTE":
        return "Sin PCI"
    if tech == "WCDMA":
        return "Sin PSC"
    return f"{tech or 'Celda'} CID {cid if cid is not None else '?'}"


def _pci_por_celda(mediciones: list, clave_de_celda) -> dict[str, int]:
    """PCI/PSC de cada celda: el primero que informó en cualquiera de sus mediciones.

    El PCI es una propiedad fija de la celda, pero la aplicación a veces lo deja vacío en alguna
    fila suelta. Resolverlo por celda, y no por tramo, evita que un tramo corto sin PCI aparezca
    con otro rótulo que el resto de la misma celda.
    """
    pci: dict[str, int] = {}
    for medicion in mediciones:
        if medicion.psc_pci is None:
            continue
        clave = clave_de_celda(medicion)
        if clave is not None:
            pci.setdefault(clave, medicion.psc_pci)
    return pci


def obtener_tramos_celda(filtros, eje: str = "celda_clave", repository=None) -> TramosCeldaOut:
    """Secuencia temporal de la celda servidora, para la gráfica escalonada (HU-C2-003).

    Los tramos se forman **siempre por celda** (`celda_clave`, el ECI en LTE), igual que en la
    detección: un cambio de tramo es un cambio de celda servidora.

    `eje` decide el rótulo y la altura de cada tramo en el eje Y:

    - `celda_clave`: una altura por celda, rotulada con su clave.
    - `psc_pci` (el que usa la interfaz): una altura por **PCI/PSC**, rotulada «PCI n» o «PSC n».
      Dos celdas que comparten PCI (p. ej. la misma antena en dos frecuencias) quedan a la misma
      altura; el marcador vertical sigue señalando el handover entre ellas.

    `valor_normalizado` se asigna **por orden de primera aparición** y no por el valor del
    identificador: así un rótulo ocupa siempre la misma altura en el eje Y aunque se cambien los
    filtros, que es lo que permite comparar dos vistas de un vistazo.
    """
    _exigir_sesiones(filtros, repository)

    mediciones = repository.obtener_mediciones_filtradas(filtros)
    eje_valor = _nombre(eje)

    if not mediciones:
        return TramosCeldaOut(eje=eje_valor, tramos=[], celdas_distintas=0)

    from app.modules.visualizacion_temporal.detector import clave_de_celda

    # Un tramo termina al cambiar de celda **o de sesión**: la misma celda en dos recorridos
    # distintos son dos permanencias, no una.
    grupos: list[list] = []
    actual = object()
    for medicion in mediciones:
        clave = clave_de_celda(medicion)
        if clave is None:
            continue
        identidad = (getattr(medicion, "sesion_id", None), clave)
        if identidad != actual:
            grupos.append([])
            actual = identidad
        grupos[-1].append(medicion)

    pci_por_celda = _pci_por_celda(mediciones, clave_de_celda)

    def rotulo(grupo: list) -> str:
        if eje_valor == "psc_pci":
            clave = clave_de_celda(grupo[0])
            return etiqueta_pci_psc(grupo[0].tech, pci_por_celda.get(clave), grupo[0].cid)
        return clave_de_celda(grupo[0])

    # Orden de primera aparición: define la altura estable de cada rótulo.
    orden: dict[str, int] = {}
    for grupo in grupos:
        orden.setdefault(rotulo(grupo), len(orden))

    total_alturas = max(len(orden), 1)
    divisor = max(total_alturas - 1, 1)

    tramos = []
    for grupo in grupos:
        primera, ultima = grupo[0], grupo[-1]
        clave = clave_de_celda(primera)
        etiqueta = rotulo(grupo)
        tramos.append(
            TramoCelda(
                inicio=primera.timestamp_medicion,
                fin=ultima.timestamp_medicion,
                celda_clave=clave,
                etiqueta=etiqueta,
                sesion_id=getattr(primera, "sesion_id", None),
                sesion_nombre=getattr(primera, "sesion_nombre", None),
                cid=primera.cid,
                node_id=primera.node_id,
                psc_pci=pci_por_celda.get(clave),
                tech=primera.tech,
                arfcn=primera.arfcn,
                n_mediciones=len(grupo),
                duracion_s=(
                    ultima.timestamp_medicion - primera.timestamp_medicion
                ).total_seconds(),
                valor_normalizado=(
                    orden[etiqueta] / divisor if total_alturas > 1 else 0.5
                ),
            )
        )

    # Celdas distintas de verdad (por clave), aunque varias compartan rótulo PCI/PSC.
    celdas = {tramo.celda_clave for tramo in tramos}
    return TramosCeldaOut(eje=eje_valor, tramos=tramos, celdas_distintas=len(celdas))


def obtener_ventana_handover(
    id_evento: str,
    segundos_antes: float = 5.0,
    segundos_despues: float = 5.0,
    parametros: list | None = None,
    repository=None,
) -> VentanaHandoverOut:
    """Ventana PRE / EVENTO / POST alrededor de un handover (HU-C2-005).

    Con muestreo a 1 Hz, ±5 s son ~11 puntos. La ventana se deja configurable porque en capturas
    con menos densidad puede hacer falta ampliarla para que la comparación se lea.
    """
    from datetime import timedelta

    fila = repository.obtener_handover(id_evento)
    if fila is None:
        raise HandoverNoEncontrado(id_evento)

    t_evento = fila["timestamp_evento"]
    mediciones = repository.obtener_mediciones_en_rango(
        str(fila["sesion_id"]),
        t_evento - timedelta(seconds=segundos_antes),
        t_evento + timedelta(seconds=segundos_despues),
    )

    nombres = [_nombre(p) for p in (parametros or PARAMETROS_RF)]

    t, t_relativo, fase = [], [], []
    series: dict[str, list] = {nombre: [] for nombre in nombres}

    for medicion in mediciones:
        delta = (medicion.timestamp_medicion - t_evento).total_seconds()
        t.append(medicion.timestamp_medicion)
        t_relativo.append(delta)
        fase.append("pre" if delta < 0 else ("evento" if delta == 0 else "post"))
        for nombre in nombres:
            valor = getattr(medicion, nombre, None)
            series[nombre].append(float(valor) if valor is not None else None)

    estadisticas = {
        nombre: _estadisticas_pre_post(series[nombre], fase) for nombre in nombres
    }

    return VentanaHandoverOut(
        evento=_fila_a_evento(fila),
        t_evento=t_evento,
        segundos_antes=segundos_antes,
        segundos_despues=segundos_despues,
        t=t,
        t_relativo_s=t_relativo,
        fase=fase,
        series=series,
        estadisticas=estadisticas,
    )


def _estadisticas_pre_post(valores: list, fases: list[str]) -> EstadisticasParametro:
    """Media antes y después del evento, y su diferencia.

    Solo entran los valores medidos. Si un lado no tiene ninguno, `delta` es `None`: no se puede
    comparar contra lo que no se midió (decisión D-5).
    """
    pre = [v for v, f in zip(valores, fases) if f == "pre" and v is not None]
    post = [v for v, f in zip(valores, fases) if f in ("evento", "post") and v is not None]

    media_pre = round(sum(pre) / len(pre), 2) if pre else None
    media_post = round(sum(post) / len(post), 2) if post else None
    delta = round(media_post - media_pre, 2) if (pre and post) else None

    return EstadisticasParametro(
        media_pre=media_pre,
        media_post=media_post,
        delta=delta,
        n_pre=len(pre),
        n_post=len(post),
        disponible=bool(pre or post),
    )


def obtener_resumen(filtros, repository=None) -> ResumenOut:
    """Resumen general del dataset analizado (HU-C2-007)."""
    _exigir_sesiones(filtros, repository)

    mediciones = repository.obtener_mediciones_filtradas(filtros)
    _, eventos = repository.listar_handovers(filtros, page=1, page_size=100000)

    from app.modules.visualizacion_temporal.detector import clave_de_celda

    claves = {clave_de_celda(m) for m in mediciones}
    claves.discard(None)

    tiempos = [m.timestamp_medicion for m in mediciones]
    inicio = min(tiempos) if tiempos else None
    fin = max(tiempos) if tiempos else None

    # Duración = suma de lo que dura **cada sesión** en el rango. Con varias sesiones de días
    # distintos, medir del primer instante al último contaría como recorrido los meses que hay
    # entre ellas y la tasa de handovers por minuto saldría prácticamente cero.
    extremos: dict[str, list] = {}
    for m in mediciones:
        par = extremos.setdefault(m.sesion_id, [m.timestamp_medicion, m.timestamp_medicion])
        par[0] = min(par[0], m.timestamp_medicion)
        par[1] = max(par[1], m.timestamp_medicion)
    duracion = (
        sum((b - a).total_seconds() for a, b in extremos.values()) if extremos else None
    )

    por_tipo: dict[str, int] = {}
    por_tecnologia: dict[str, int] = {}
    for evento in eventos:
        tipo = evento.get("tipo_evento") or "desconocido"
        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
        tec = evento.get("tipo_tecnologia") or "desconocida"
        por_tecnologia[tec] = por_tecnologia.get(tec, 0) + 1

    return ResumenOut(
        total_handovers=len(eventos),
        radiobases_involucradas=len(claves),
        # Sesiones distintas **con mediciones en el rango filtrado**: una sesión elegida que
        # los filtros dejan vacía no se ha analizado.
        sesiones_analizadas=len({m.sesion_id for m in mediciones}),
        n_mediciones=len(mediciones),
        ventana_inicio=inicio,
        ventana_fin=fin,
        duracion_s=duracion,
        por_tipo=por_tipo,
        por_tecnologia=por_tecnologia,
        total_ping_pong=sum(1 for e in eventos if e.get("ping_pong")),
        total_confianza_baja=sum(1 for e in eventos if e.get("confianza") == "baja"),
        tasa_ho_por_minuto=(
            round(len(eventos) / (duracion / 60), 3) if duracion and duracion > 0 else None
        ),
        # `_construir_cobertura` acumula filas por parámetro, así que concatenar la cobertura de
        # cada sesión da el total conjunto.
        cobertura_parametros=_construir_cobertura(
            [
                fila
                for sesion_id in _sesiones_de(filtros)
                for fila in repository.obtener_cobertura_parametros(sesion_id)
            ],
            mediciones,
        ),
    )


#: Duración en segundos de cada intervalo de análisis del histograma (HU-C2-008).
_DURACION_INTERVALO_S = {"hora": 3600, "10min": 600, "5min": 300}


@dataclass
class _Visita:
    """Una vuelta a una celda (o a un PCI/PSC): uno o varios tramos seguidos de la misma sesión."""

    clave: str
    inicio: datetime
    fin: datetime
    sesion_id: str | None
    sesion_nombre: str | None
    n_mediciones: int
    duracion_s: float
    tramos: list = field(default_factory=list)


def _visitas(tramos: list, eje: str) -> list[_Visita]:
    """Convierte los tramos en visitas según el identificador elegido.

    - `celda_clave`: cada tramo es una visita a su celda.
    - `psc_pci`: tramos **seguidos** con el mismo PCI/PSC son **una sola** visita. Pasar de la
      celda de 700 MHz a la de 850 MHz de la misma antena, con el mismo PCI, no es «volver» a
      ese PCI: el teléfono nunca lo dejó. Así el histograma cuenta lo mismo que se ve en la
      secuencia de radiobases, donde esos tramos quedan a la misma altura.
    """
    visitas: list[_Visita] = []
    for tramo in tramos:
        clave = tramo.etiqueta if eje == "psc_pci" else tramo.celda_clave
        anterior = visitas[-1] if visitas else None
        if (
            eje == "psc_pci"
            and anterior is not None
            and anterior.clave == clave
            and anterior.sesion_id == tramo.sesion_id
        ):
            anterior.fin = tramo.fin
            anterior.n_mediciones += tramo.n_mediciones
            anterior.duracion_s += tramo.duracion_s
            anterior.tramos.append(tramo)
            continue

        visitas.append(
            _Visita(
                clave=clave,
                inicio=tramo.inicio,
                fin=tramo.fin,
                sesion_id=tramo.sesion_id,
                sesion_nombre=tramo.sesion_nombre,
                n_mediciones=tramo.n_mediciones,
                duracion_s=tramo.duracion_s,
                tramos=[tramo],
            )
        )
    return visitas


def _minutos_de_la_sesion_mas_larga(tramos_por_sesion: dict[str, list]) -> int:
    """Minutos, redondeados hacia arriba, que dura la sesión más larga (mínimo 1)."""
    duraciones = [
        (max(t.fin for t in tramos) - min(t.inicio for t in tramos)).total_seconds()
        for tramos in tramos_por_sesion.values()
    ]
    return max(1, math.ceil(max(duraciones, default=0) / 60))


def _intervalos_por_sesion(tramos_por_sesion: dict[str, list], duracion_s: int) -> list[tuple]:
    """Reparte los tramos en intervalos de `duracion_s` contados desde el inicio de cada sesión.

    Cada sesión empieza su propio primer intervalo. Contar desde el primer instante de todas
    juntas partiría por la mitad a una sesión que empezó a media hora de otra, y con sesiones de
    días distintos los intervalos de la segunda no empezarían nunca en su comienzo.
    """
    grupos = []
    for sesion_id, tramos in tramos_por_sesion.items():
        origen = min(t.inicio for t in tramos)
        por_indice: dict[int, list] = {}
        for tramo in tramos:
            indice = int((tramo.inicio - origen).total_seconds() // duracion_s)
            por_indice.setdefault(indice, []).append(tramo)

        for indice in sorted(por_indice):
            grupos.append(
                (
                    origen + timedelta(seconds=indice * duracion_s),
                    origen + timedelta(seconds=(indice + 1) * duracion_s),
                    sesion_id,
                    tramos[0].sesion_nombre,
                    por_indice[indice],
                )
            )

    # Orden cronológico: las sesiones una tras otra y, dentro de cada una, sus intervalos.
    return sorted(grupos, key=lambda grupo: grupo[0])


def obtener_celdas_repetidas(
    filtros,
    intervalo: str = "total",
    top: int = 20,
    repository=None,
    minutos: int | None = None,
    eje: str = "celda_clave",
) -> CeldasRepetidasOut:
    """Distribución de radiobases repetidas (HU-C2-008).

    Una "visita" es una permanencia: si el terminal vuelve más tarde, cuenta otra vez. Es justo lo
    que revela los patrones de permanencia y las zonas de solapamiento.

    `eje` decide qué se cuenta (`_visitas`): cada celda (`celda_clave`) o cada PCI/PSC
    (`psc_pci`, el que usa la interfaz). Por PCI/PSC, las celdas que lo comparten suman en la
    misma barra.

    El intervalo se puede dar en `minutos` (lo que mueve el deslizador de la interfaz) o con uno
    de los intervalos fijos de `intervalo`; `minutos` tiene prioridad. Sin ninguno de los dos se
    analiza el total.
    """
    _exigir_sesiones(filtros, repository)

    intervalo_valor = _nombre(intervalo)
    eje_valor = _nombre(eje)
    tramos = _visitas(
        obtener_tramos_celda(filtros, eje=eje_valor, repository=repository).tramos, eje_valor
    )

    duracion_s = minutos * 60 if minutos else _DURACION_INTERVALO_S.get(intervalo_valor)
    minutos_efectivos = duracion_s // 60 if duracion_s else None

    if not tramos:
        return CeldasRepetidasOut(
            intervalo=intervalo_valor,
            minutos=minutos_efectivos,
            eje=eje_valor,
            top=top,
            bins=[],
            total_celdas=0,
        )

    tramos_por_sesion: dict[str, list] = {}
    for tramo in tramos:
        tramos_por_sesion.setdefault(tramo.sesion_id, []).append(tramo)

    if duracion_s is None:
        grupos = [(None, None, None, None, tramos)]
    else:
        grupos = _intervalos_por_sesion(tramos_por_sesion, duracion_s)

    bins = []
    todas_las_claves: set[str] = set()
    for inicio, fin, sesion_id, sesion_nombre, visitas_bin in grupos:
        acumulado: dict[str, dict] = {}
        for visita in visitas_bin:
            todas_las_claves.add(visita.clave)
            primera = visita.tramos[0]
            entrada = acumulado.setdefault(
                visita.clave,
                {
                    "celda_clave": primera.celda_clave,
                    "etiqueta": etiqueta_pci_psc(primera.tech, primera.psc_pci, primera.cid),
                    "cid": primera.cid,
                    "node_id": primera.node_id,
                    "psc_pci": primera.psc_pci,
                    "tech": primera.tech,
                    "arfcn": primera.arfcn,
                    "celdas_incluidas": [],
                    "canales": [],
                    "n_visitas": 0,
                    "n_mediciones": 0,
                    "tiempo_total_s": 0.0,
                },
            )
            for tramo in visita.tramos:
                if tramo.celda_clave not in entrada["celdas_incluidas"]:
                    entrada["celdas_incluidas"].append(tramo.celda_clave)
                if tramo.arfcn is not None and tramo.arfcn not in entrada["canales"]:
                    entrada["canales"].append(tramo.arfcn)
            entrada["n_visitas"] += 1
            entrada["n_mediciones"] += visita.n_mediciones
            entrada["tiempo_total_s"] += visita.duracion_s

        celdas = sorted(
            (CeldaRepetida(**datos) for datos in acumulado.values()),
            key=lambda c: (-c.n_visitas, -c.tiempo_total_s, c.etiqueta, c.celda_clave),
        )[:top]
        bins.append(
            BinIntervalo(
                inicio=inicio,
                fin=fin,
                sesion_id=sesion_id,
                sesion_nombre=sesion_nombre,
                celdas=celdas,
            )
        )

    return CeldasRepetidasOut(
        intervalo=intervalo_valor,
        minutos=minutos_efectivos,
        minutos_max=_minutos_de_la_sesion_mas_larga(tramos_por_sesion),
        eje=eje_valor,
        top=top,
        bins=bins,
        total_celdas=len(todas_las_claves),
    )


# ================================================================================================
# Disponibilidad de datos — calendario y filtros
# ================================================================================================

#: Pausa, en minutos, a partir de la cual dos ratos de captura del mismo día se ofrecen como
#: franjas horarias separadas. Se tolera un minuto suelto sin filas para no partir una franja por
#: un corte breve de la aplicación de medición.
PAUSA_ENTRE_FRANJAS_MIN = 2


def agrupar_en_franjas(minutos: list[dt_time]) -> list[FranjaHoraria]:
    """Junta los minutos con mediciones de un día en franjas continuas.

    Ejemplo: 16:24, 16:25 … 16:45 y 18:02 … 18:10 dan dos franjas, 16:24–16:45 y 18:02–18:10.
    """
    franjas: list[list[int]] = []
    for minuto in sorted({m.hour * 60 + m.minute for m in minutos}):
        if franjas and minuto - franjas[-1][1] <= PAUSA_ENTRE_FRANJAS_MIN:
            franjas[-1][1] = minuto
        else:
            franjas.append([minuto, minuto])

    return [
        FranjaHoraria(inicio=dt_time(a // 60, a % 60), fin=dt_time(b // 60, b % 60))
        for a, b in franjas
    ]


def obtener_disponibilidad(filtros, repository) -> DisponibilidadOut:
    """Días, franjas horarias y tecnologías con datos en las sesiones elegidas.

    Todo se calcula en la zona horaria del usuario: un recorrido que en UTC cae a las 00:30 del
    día siguiente, en Ecuador es de las 19:30 del día anterior, y es ese día el que el usuario
    buscará en el calendario.
    """
    _exigir_sesiones(filtros, repository)

    sesiones = _sesiones_de(filtros)
    zona = getattr(filtros, "zona_horaria", None) or "UTC"

    por_dia: dict = {}
    for fila in repository.contar_mediciones_por_minuto(sesiones, zona):
        dia = por_dia.setdefault(fila["fecha"], {"n_mediciones": 0, "minutos": []})
        dia["n_mediciones"] += int(fila["n_mediciones"])
        dia["minutos"].append(fila["minuto"])

    handovers = {
        fila["fecha"]: int(fila["n_handovers"])
        for fila in repository.contar_handovers_por_dia(sesiones, zona)
    }

    return DisponibilidadOut(
        zona_horaria=zona,
        dias=[
            DiaDisponible(
                fecha=fecha,
                n_mediciones=dia["n_mediciones"],
                n_handovers=handovers.get(fecha, 0),
                franjas=agrupar_en_franjas(dia["minutos"]),
            )
            for fecha, dia in sorted(por_dia.items())
        ],
        tecnologias=repository.listar_tecnologias(sesiones),
    )


def listar_handovers(filtros, page: int, page_size: int, orden: str, repository) -> PaginaHandovers:
    """Página de eventos para la tabla de HU-C2-009."""
    _exigir_sesiones(filtros, repository)

    total, filas = repository.listar_handovers(filtros, page=page, page_size=page_size, orden=orden)

    return PaginaHandovers(
        total=total,
        page=page,
        page_size=page_size,
        items=[_fila_a_evento(fila) for fila in filas],
    )


def _fila_a_evento(fila: dict) -> EventoHandover:
    """Traduce una fila de `eventos_handover` al contrato de salida."""
    return EventoHandover(
        id_evento=str(fila["id_evento"]),
        sesion_id=str(fila["sesion_id"]),
        sesion_nombre=fila.get("sesion_nombre"),
        timestamp_evento=fila["timestamp_evento"],
        report_index_evento=fila.get("report_index_evento"),
        celda_origen=CeldaResumen(
            clave=fila["celda_origen_clave"],
            cid=fila.get("celda_origen_cid"),
            node_id=fila.get("celda_origen_node_id"),
            psc_pci=fila.get("celda_origen_psc_pci"),
            arfcn=fila.get("celda_origen_arfcn"),
            tech=fila.get("celda_origen_tech"),
        ),
        celda_destino=CeldaResumen(
            clave=fila["celda_destino_clave"],
            cid=fila.get("celda_destino_cid"),
            node_id=fila.get("celda_destino_node_id"),
            psc_pci=fila.get("celda_destino_psc_pci"),
            arfcn=fila.get("celda_destino_arfcn"),
            tech=fila.get("celda_destino_tech"),
        ),
        medicion_previa_id=str(fila.get("medicion_previa_id") or ""),
        medicion_posterior_id=str(fila.get("medicion_posterior_id") or ""),
        tipo_evento=fila["tipo_evento"],
        ping_pong=bool(fila.get("ping_pong")),
        tipo_tecnologia=fila.get("tipo_tecnologia"),
        confianza=fila.get("confianza") or "alta",
        data_state_evento=fila.get("data_state_evento"),
        delta_rsrp_db=fila.get("delta_rsrp_db"),
        delta_rsrq_db=fila.get("delta_rsrq_db"),
        delta_rssnr_db=fila.get("delta_rssnr_db"),
        delta_rscp_db=fila.get("delta_rscp_db"),
        delta_rssi_db=fila.get("delta_rssi_db"),
        duracion_permanencia_s=float(fila.get("duracion_permanencia_s") or 0.0),
        muestras_confirmacion=int(fila.get("muestras_confirmacion") or 0),
    )
