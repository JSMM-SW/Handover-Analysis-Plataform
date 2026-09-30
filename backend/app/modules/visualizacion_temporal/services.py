"""
Servicios del Módulo 2 — Capa 3, orquestación.

Coordina repositorio y detector, pero **no ejecuta SQL ni conoce FastAPI**: recibe un repositorio
ya construido y lanza excepciones de dominio, que el router traduce a códigos HTTP
(`docs/02-arquitectura.md`).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

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
    EstadisticasParametro,
    EventoHandover,
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
            origen=fila.get("origen"),
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


def obtener_tramos_celda(filtros, eje: str = "celda_clave", repository=None) -> TramosCeldaOut:
    """Secuencia temporal de la celda servidora, para la gráfica escalonada (HU-C2-003).

    `valor_normalizado` se asigna **por orden de primera aparición** y no por el valor del
    identificador: así una celda ocupa siempre la misma altura en el eje Y aunque se cambien los
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

    # Orden de primera aparición: define la altura estable de cada celda.
    orden: dict[str, int] = {}
    for grupo in grupos:
        clave = clave_de_celda(grupo[0])
        orden.setdefault(clave, len(orden))

    total_celdas = max(len(orden), 1)
    divisor = max(total_celdas - 1, 1)

    tramos = []
    for grupo in grupos:
        primera, ultima = grupo[0], grupo[-1]
        clave = clave_de_celda(primera)
        etiqueta = (
            str(primera.psc_pci) if eje_valor == "psc_pci" and primera.psc_pci is not None
            else clave
        )
        tramos.append(
            TramoCelda(
                inicio=primera.timestamp_medicion,
                fin=ultima.timestamp_medicion,
                celda_clave=clave,
                etiqueta=etiqueta,
                cid=primera.cid,
                node_id=primera.node_id,
                psc_pci=primera.psc_pci,
                tech=primera.tech,
                arfcn=primera.arfcn,
                n_mediciones=len(grupo),
                duracion_s=(
                    ultima.timestamp_medicion - primera.timestamp_medicion
                ).total_seconds(),
                valor_normalizado=(
                    orden[clave] / divisor if total_celdas > 1 else 0.5
                ),
            )
        )

    return TramosCeldaOut(eje=eje_valor, tramos=tramos, celdas_distintas=len(orden))


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


def obtener_celdas_repetidas(
    filtros, intervalo: str = "total", top: int = 20, repository=None
) -> CeldasRepetidasOut:
    """Distribución de radiobases repetidas (HU-C2-008).

    Una "visita" es un tramo: si el terminal vuelve a la misma celda más tarde, cuenta otra vez.
    Es justo lo que revela los patrones de permanencia y las zonas de solapamiento.
    """
    _exigir_sesiones(filtros, repository)

    intervalo_valor = _nombre(intervalo)
    tramos = obtener_tramos_celda(filtros, repository=repository).tramos

    if not tramos:
        return CeldasRepetidasOut(intervalo=intervalo_valor, top=top, bins=[], total_celdas=0)

    if intervalo_valor == "total":
        grupos = [(None, None, tramos)]
    else:
        duracion = _DURACION_INTERVALO_S[intervalo_valor]
        origen = min(t.inicio for t in tramos)
        por_bin: dict[int, list] = {}
        for tramo in tramos:
            indice = int((tramo.inicio - origen).total_seconds() // duracion)
            por_bin.setdefault(indice, []).append(tramo)

        from datetime import timedelta

        grupos = [
            (
                origen + timedelta(seconds=indice * duracion),
                origen + timedelta(seconds=(indice + 1) * duracion),
                por_bin[indice],
            )
            for indice in sorted(por_bin)
        ]

    bins = []
    todas_las_celdas: set[str] = set()
    for inicio, fin, tramos_bin in grupos:
        acumulado: dict[str, dict] = {}
        for tramo in tramos_bin:
            todas_las_celdas.add(tramo.celda_clave)
            entrada = acumulado.setdefault(
                tramo.celda_clave,
                {
                    "celda_clave": tramo.celda_clave,
                    "cid": tramo.cid,
                    "node_id": tramo.node_id,
                    "psc_pci": tramo.psc_pci,
                    "tech": tramo.tech,
                    "n_visitas": 0,
                    "n_mediciones": 0,
                    "tiempo_total_s": 0.0,
                },
            )
            entrada["n_visitas"] += 1
            entrada["n_mediciones"] += tramo.n_mediciones
            entrada["tiempo_total_s"] += tramo.duracion_s

        celdas = sorted(
            (CeldaRepetida(**datos) for datos in acumulado.values()),
            key=lambda c: (-c.n_visitas, -c.tiempo_total_s, c.celda_clave),
        )[:top]
        bins.append(BinIntervalo(inicio=inicio, fin=fin, celdas=celdas))

    return CeldasRepetidasOut(
        intervalo=intervalo_valor, top=top, bins=bins, total_celdas=len(todas_las_celdas)
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
    """Traduce una fila de `v_vt_evento_detalle` al contrato de salida."""
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
