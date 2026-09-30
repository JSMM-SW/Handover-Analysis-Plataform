/**
 * Transformación de las respuestas del backend a opciones de ECharts (Capa 2).
 *
 * Aquí vive toda la lógica de las gráficas; los componentes solo montan `<ReactECharts>` con lo
 * que devuelven estos hooks (regla 5 de CLAUDE.md). Las funciones puras se exportan aparte para
 * poder probarlas sin renderizar nada.
 */

import { useMemo } from 'react';

import { ETIQUETAS_RF, ETIQUETAS_TIPO_EVENTO } from '../types/index.js';
import { ESTILO_EJE, ESTILO_TOOLTIP, TEMA } from '../utils/temaVisual.js';

/** Fusiona el estilo común de ejes con lo propio de cada eje, sin perder los sub-objetos. */
function eje(propio = {}) {
  return {
    ...ESTILO_EJE,
    ...propio,
    axisLabel: { ...ESTILO_EJE.axisLabel, ...propio.axisLabel },
    nameTextStyle: { ...ESTILO_EJE.nameTextStyle, ...propio.nameTextStyle },
    splitLine: propio.splitLine ?? ESTILO_EJE.splitLine,
  };
}

/** Deslizador de zoom en azul pastel: discreto, pero con asas fáciles de agarrar. */
const DESLIZADOR_ZOOM = {
  type: 'slider',
  height: 20,
  bottom: 12,
  borderColor: 'transparent',
  backgroundColor: TEMA.claro,
  fillerColor: 'rgba(127,181,218,0.18)',
  dataBackground: {
    lineStyle: { color: TEMA.acentoBorde, width: 1 },
    areaStyle: { color: TEMA.acentoTenue, opacity: 0.8 },
  },
  selectedDataBackground: {
    lineStyle: { color: TEMA.acento, width: 1 },
    areaStyle: { color: TEMA.acentoBorde, opacity: 0.5 },
  },
  handleStyle: { color: TEMA.superficie, borderColor: TEMA.acento, borderWidth: 1.2 },
  moveHandleStyle: { color: TEMA.acentoBorde, opacity: 0.7 },
  emphasis: { handleStyle: { borderColor: TEMA.acentoFuerte } },
  textStyle: { color: TEMA.textoSuave, fontSize: 10 },
};

/**
 * Eje Y de cada parámetro.
 *
 * RSRP/RSCP/RSSI son **potencias en dBm** (−140…−40) y RSRQ/SINR son **relaciones en dB**
 * (−20…+30). Compartir eje aplastaría las dos curvas contra los extremos y no se vería nada, así
 * que van a ejes distintos: 0 = izquierda (dBm), 1 = derecha (dB).
 */
export const EJE_POR_PARAMETRO = {
  rsrp_dbm: 0,
  rscp_dbm: 0,
  rssi_dbm: 0,
  rsrq_db: 1,
  rssnr_db: 1,
};

/**
 * Da una marca de tiempo real a los cortes de línea que el backend envía como `null` en `t`.
 *
 * El backend usa un `null` en el eje de tiempos para indicar «aquí no hubo captura». Pero un eje
 * `type: 'time'` de ECharts **no puede trabajar con una coordenada X nula**: al calcular la
 * extensión del eje produce `NaN` y el gráfico se queda colgado, bloqueando la pestaña.
 *
 * La forma correcta de cortar una línea es dar un instante válido con **valor Y nulo**. Aquí se
 * sitúa ese punto en el punto medio del hueco, que es donde visualmente corresponde.
 */
export function instantesConHuecosDatables(t = []) {
  return t.map((instante, indice) => {
    if (instante !== null && instante !== undefined) return instante;

    const anterior = t.slice(0, indice).reverse().find(Boolean);
    const siguiente = t.slice(indice + 1).find(Boolean);

    if (anterior && siguiente) {
      const medio = (new Date(anterior).getTime() + new Date(siguiente).getTime()) / 2;
      return new Date(medio).toISOString();
    }
    return anterior ?? siguiente ?? null;
  });
}

/** Formatea un instante ISO como hora local legible. */
export function formatearHora(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString('es-EC', { hour12: false });
}

/** Formatea un instante ISO con fecha y hora. */
export function formatearFechaHora(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('es-EC', { hour12: false });
}

/**
 * Convierte la respuesta columnar de `GET /series` en series de ECharts.
 *
 * Dos detalles que importan:
 * - Se emparejan `t` y cada serie por índice, así que **los `null` se conservan**: un hueco de
 *   captura (null en `t`) y una medida ausente (null en la serie) llegan a la gráfica como
 *   puntos nulos, y con `connectNulls: false` ECharts corta la línea en lugar de inventar un
 *   segmento recto sobre datos que no existen.
 * - Un parámetro sin ninguna medida se devuelve igualmente, con `sinDatos: true`, para que la
 *   interfaz pueda avisar en vez de mostrar una gráfica vacía sin explicación (decisión D-5).
 *
 * @param {import('../types/index.js').Series|null} respuesta
 * @param {import('../types/index.js').ParametroRF[]} parametros
 */
export function construirSeriesEcharts(respuesta, parametros = []) {
  if (!respuesta?.t?.length) return [];

  const cobertura = new Map((respuesta.cobertura ?? []).map((c) => [c.parametro, c]));
  const instantes = instantesConHuecosDatables(respuesta.t);

  return parametros
    .filter((parametro) => respuesta.series?.[parametro])
    .map((parametro) => {
      const valores = respuesta.series[parametro];
      const meta = ETIQUETAS_RF[parametro];
      const datos = instantes.map((instante, indice) => [instante, valores[indice] ?? null]);

      return {
        id: parametro,
        name: meta.etiqueta,
        type: 'line',
        yAxisIndex: EJE_POR_PARAMETRO[parametro] ?? 0,
        data: datos,
        showSymbol: false,
        connectNulls: false,
        // Trazo fino: con varias capas activas, las líneas gruesas se tapan unas a otras.
        lineStyle: { width: 1.3, color: meta.color },
        itemStyle: { color: meta.color },
        emphasis: { focus: 'series', lineStyle: { width: 2 } },
        // Rendimiento: con series largas ECharts usa una ruta de dibujado optimizada.
        large: true,
        largeThreshold: 2000,
        sampling: 'lttb',
        sinDatos: !(cobertura.get(parametro)?.disponible ?? valores.some((v) => v !== null)),
      };
    });
}

/**
 * Construye los marcadores verticales de handover (`markLine`) — CA2 de HU-C2-002 y HU-C2-004.
 *
 * El marcador destacado (el evento seleccionado en la tabla) se pinta más grueso y en otro color
 * para que se localice de un vistazo tras el zoom automático.
 */
export function construirMarcadoresHO(handovers = [], idDestacado = null) {
  if (!handovers.length) return null;

  return {
    silent: false,
    symbol: ['none', 'none'],
    label: { show: false },
    emphasis: { lineStyle: { width: 2 }, label: { show: false } },
    data: handovers.map((ho) => {
      const destacado = ho.id_evento === idDestacado;
      return {
        xAxis: ho.timestamp_evento,
        // Se guardan para el tooltip: ECharts conserva las claves desconocidas.
        idEvento: ho.id_evento,
        origen: ho.celda_origen?.clave,
        destino: ho.celda_destino?.clave,
        tipoEvento: ho.tipo_evento,
        pingPong: ho.ping_pong,
        lineStyle: destacado
          ? {
              // El evento elegido en la tabla: otro color (frambuesa), más grueso y con sombra,
              // para localizarlo de un vistazo tras el zoom automático.
              color: TEMA.marcadorHOSeleccionado,
              width: 2.6,
              type: 'solid',
              opacity: 1,
              shadowColor: 'rgba(194,24,91,0.45)',
              shadowBlur: 10,
            }
          : {
              // Todos los demás se dibujan **siempre**, en línea continua de un solo color: son
              // el mapa de dónde ocurrieron los traspasos.
              color: TEMA.marcadorHO,
              width: 1.2,
              type: 'solid',
              opacity: 0.9,
            },
      };
    }),
  };
}

/** Tooltip de un marcador de handover: celda origen → destino y la hora exacta (CA3 de HU-002). */
function tooltipMarcador(parametro) {
  const { origen, destino, tipoEvento, pingPong } = parametro.data ?? {};
  const hora = formatearFechaHora(parametro.data?.xAxis);

  return [
    `<strong style="color:${TEMA.acentoFuerte}">Handover</strong>`,
    `<div style="margin:4px 0;color:${TEMA.textoSuave}">${hora}</div>`,
    `<div>${origen ?? '—'} → ${destino ?? '—'}</div>`,
    `<div style="color:${TEMA.textoSuave}">${ETIQUETAS_TIPO_EVENTO[tipoEvento] ?? tipoEvento ?? ''}${
      pingPong ? ' · ping-pong' : ''
    }</div>`,
  ].join('');
}

/**
 * Opción completa del timeline maestro (HU-C2-002 y HU-C2-004).
 *
 * @param {Object} args
 * @param {import('../types/index.js').Series|null} args.datos
 * @param {import('../types/index.js').ParametroRF[]} args.parametros
 * @param {import('../types/index.js').Handover[]} args.handovers
 * @param {boolean} args.mostrarMarcadores
 * @param {string|null} args.idDestacado
 */
export function useOpcionTimeline({
  datos,
  parametros,
  handovers = [],
  mostrarMarcadores = true,
  idDestacado = null,
}) {
  return useMemo(() => {
    const series = construirSeriesEcharts(datos, parametros);
    const marcadores = mostrarMarcadores ? construirMarcadoresHO(handovers, idDestacado) : null;

    // Los marcadores se cuelgan de la primera serie: ECharts los dibuja una sola vez y quedan
    // por encima de todas las curvas.
    if (marcadores && series.length) {
      series[0] = { ...series[0], markLine: marcadores };
    }

    const hayEjeDerecho = series.some((s) => s.yAxisIndex === 1);

    return {
      animation: false,
      // Sin leyenda interna: la barra de capas sobre la gráfica ya hace de leyenda, con el
      // mismo color por parámetro, y así el área de dibujo queda despejada.
      legend: { show: false },
      grid: { left: 52, right: hayEjeDerecho ? 52 : 20, top: 20, bottom: 64 },
      tooltip: {
        ...ESTILO_TOOLTIP,
        trigger: 'axis',
        axisPointer: { type: 'line', snap: true, lineStyle: { color: TEMA.acentoBorde } },
        confine: true,
        formatter: (parametros_) => {
          const lista = Array.isArray(parametros_) ? parametros_ : [parametros_];
          if (lista[0]?.componentType === 'markLine') return tooltipMarcador(lista[0]);

          const instante = lista[0]?.axisValueLabel ?? lista[0]?.axisValue;
          const filas = lista
            .filter((p) => p.data?.[1] !== null && p.data?.[1] !== undefined)
            .map((p) => `${p.marker} ${p.seriesName}: <strong>${p.data[1]}</strong>`);

          if (!filas.length) {
            return `${formatearFechaHora(instante)}<br/><span style="color:${TEMA.textoSuave}">Sin medidas válidas</span>`;
          }
          return `${formatearFechaHora(instante)}<br/>${filas.join('<br/>')}`;
        },
      },
      xAxis: eje({
        type: 'time',
        axisLabel: { hideOverlap: true },
        splitLine: { show: false },
      }),
      yAxis: [
        eje({ type: 'value', name: 'dBm', scale: true }),
        eje({
          type: 'value',
          name: 'dB',
          scale: true,
          show: hayEjeDerecho,
          splitLine: { show: false },
        }),
      ],
      dataZoom: [{ type: 'inside', throttle: 80 }, DESLIZADOR_ZOOM],
      series,
    };
  }, [datos, parametros, handovers, mostrarMarcadores, idDestacado]);
}

/**
 * Opción de la gráfica escalonada de radiobases (HU-C2-003).
 *
 * Se dibuja con `step: 'end'` porque la celda servidora **no cambia progresivamente**: se mantiene
 * y salta. Una línea interpolada sugeriría una transición gradual que no existe.
 *
 * Cada tramo aporta dos puntos (inicio y fin) y entre tramos se inserta un nulo, de modo que un
 * hueco de captura no se dibuje como una permanencia continua.
 */
export function useOpcionSecuenciaCeldas({
  tramos = [],
  handovers = [],
  mostrarMarcadores = true,
  idDestacado = null,
  eje: ejeCeldas = 'celda_clave',
}) {
  return useMemo(() => {
    const datos = [];
    const porValor = new Map();

    tramos.forEach((tramo, indice) => {
      if (indice > 0) datos.push([tramos[indice - 1].fin, null]);
      datos.push([tramo.inicio, tramo.valor_normalizado, tramo]);
      datos.push([tramo.fin, tramo.valor_normalizado, tramo]);
      porValor.set(tramo.valor_normalizado, tramo.etiqueta);
    });

    const serie = {
      name: 'Celda servidora',
      type: 'line',
      step: 'end',
      data: datos,
      showSymbol: false,
      connectNulls: false,
      lineStyle: { width: 1.6, color: TEMA.acento },
      itemStyle: { color: TEMA.acento },
      areaStyle: { opacity: 0.1, color: TEMA.acentoBorde },
    };

    const marcadores = mostrarMarcadores ? construirMarcadoresHO(handovers, idDestacado) : null;
    if (marcadores) serie.markLine = marcadores;

    return {
      animation: false,
      grid: { left: 52, right: 20, top: 16, bottom: 30 },
      tooltip: {
        ...ESTILO_TOOLTIP,
        trigger: 'axis',
        axisPointer: { type: 'line', lineStyle: { color: TEMA.acentoBorde } },
        confine: true,
        formatter: (parametros_) => {
          const lista = Array.isArray(parametros_) ? parametros_ : [parametros_];
          if (lista[0]?.componentType === 'markLine') return tooltipMarcador(lista[0]);

          const tramo = lista[0]?.data?.[2];
          if (!tramo) return '';

          return [
            `<strong>${tramo.etiqueta}</strong>`,
            `<div style="margin-top:4px">Celda: ${tramo.celda_clave}</div>`,
            tramo.psc_pci != null ? `<div>PCI: ${tramo.psc_pci}</div>` : '',
            tramo.tech ? `<div>Tecnología: ${tramo.tech}</div>` : '',
            `<div>Permanencia: ${Math.round(tramo.duracion_s)} s · ${tramo.n_mediciones} mediciones</div>`,
            `<div style="color:${TEMA.textoSuave}">${formatearHora(tramo.inicio)} → ${formatearHora(tramo.fin)}</div>`,
          ]
            .filter(Boolean)
            .join('');
        },
      },
      xAxis: eje({ type: 'time', axisLabel: { hideOverlap: true }, splitLine: { show: false } }),
      yAxis: eje({
        type: 'value',
        min: -0.06,
        max: 1.06,
        name: ejeCeldas === 'psc_pci' ? 'PCI' : 'Celda',
        axisLabel: {
          fontSize: 10,
          // El eje Y es una altura normalizada; se rotula con la celda que ocupa cada altura.
          formatter: (valor) => porValor.get(valor) ?? '',
        },
      }),
      series: [serie],
    };
  }, [tramos, handovers, mostrarMarcadores, idDestacado, ejeCeldas]);
}

/**
 * Rango de zoom centrado en un evento, para el clic en una fila de la tabla (estructura V1 §3).
 *
 * Se abre una ventana de `factor` veces la ventana de detalle a cada lado: suficiente para ver el
 * antes y el después sin perder de vista el contexto.
 *
 * @returns {[string, string]} par de instantes ISO
 */
export function rangoAlrededorDe(timestampEvento, ventanaSegundos = 5, factor = 6) {
  const centro = new Date(timestampEvento).getTime();
  const margen = ventanaSegundos * factor * 1000;

  return [new Date(centro - margen).toISOString(), new Date(centro + margen).toISOString()];
}

// ================================================================================================
// Fase 6 — ventana PRE/POST e histograma de radiobases
// ================================================================================================

/** Sombreado de las zonas PRE y POST: azul pastel antes, verde pastel después. */
export const SOMBREADO_VENTANA = {
  pre: 'rgba(127,181,218,0.18)',
  post: 'rgba(127,203,159,0.18)',
};

/** Rótulo de zona dentro del sombreado. */
function rotuloZona(texto) {
  return {
    show: true,
    position: 'insideTop',
    distance: 6,
    formatter: texto,
    fontSize: 10,
    fontWeight: 600,
    color: TEMA.acentoFuerte,
  };
}

/**
 * Opción de la gráfica de ventana alrededor de un handover (HU-C2-005).
 *
 * El eje X son **segundos relativos al evento** (−5 … 0 … +5) y no la hora absoluta: para comparar
 * el antes y el después lo que importa es la distancia al traspaso, no qué hora era.
 *
 * El fondo se sombrea en dos tonos pastel, azul para `pre` y verde para `post`. Ese sombreado es
 * lo que hace posible de un vistazo la comparación pre/post que pide el alcance de la tesis; sin
 * él, la línea vertical en t=0 se pierde entre las curvas.
 */
export function useOpcionVentana({ datos, parametros = [] }) {
  return useMemo(() => {
    if (!datos?.t_relativo_s?.length) return null;

    const nombres = parametros.length ? parametros : Object.keys(datos.series ?? {});

    const series = nombres
      .filter((parametro) => datos.series?.[parametro])
      .map((parametro) => {
        const meta = ETIQUETAS_RF[parametro];
        return {
          id: parametro,
          name: meta?.etiqueta ?? parametro,
          type: 'line',
          yAxisIndex: EJE_POR_PARAMETRO[parametro] ?? 0,
          data: datos.t_relativo_s.map((segundo, indice) => [
            segundo,
            datos.series[parametro][indice] ?? null,
          ]),
          connectNulls: false,
          showSymbol: true,
          symbol: 'circle',
          symbolSize: 4,
          lineStyle: { width: 1.6, color: meta?.color },
          itemStyle: { color: meta?.color, borderColor: TEMA.superficie, borderWidth: 1 },
        };
      });

    const minimo = Math.min(...datos.t_relativo_s);
    const maximo = Math.max(...datos.t_relativo_s);

    // El sombreado y la línea del evento se cuelgan de la primera serie para dibujarse una vez.
    if (series.length) {
      series[0] = {
        ...series[0],
        markArea: {
          silent: true,
          data: [
            [
              { xAxis: minimo, itemStyle: { color: SOMBREADO_VENTANA.pre }, label: rotuloZona('ANTES · PRE') },
              { xAxis: 0 },
            ],
            [
              { xAxis: 0, itemStyle: { color: SOMBREADO_VENTANA.post }, label: rotuloZona('DESPUÉS · POST') },
              { xAxis: maximo },
            ],
          ],
        },
        markLine: {
          silent: true,
          symbol: ['none', 'none'],
          data: [{ xAxis: 0 }],
          lineStyle: { color: TEMA.marcadorHOSeleccionado, width: 2, type: 'solid' },
          // Sin rótulo: chocaba con el nombre del eje, y la leyenda de zonas ya lo explica.
          label: { show: false },
        },
      };
    }

    const hayEjeDerecho = series.some((s) => s.yAxisIndex === 1);

    return {
      animation: false,
      grid: { left: 48, right: hayEjeDerecho ? 48 : 20, top: 44, bottom: 44 },
      legend: {
        top: 0,
        left: 0,
        type: 'scroll',
        icon: 'circle',
        itemWidth: 8,
        itemHeight: 8,
        itemGap: 14,
        textStyle: { fontSize: 11, color: TEMA.textoSuave },
      },
      tooltip: {
        ...ESTILO_TOOLTIP,
        trigger: 'axis',
        axisPointer: { type: 'line', lineStyle: { color: TEMA.acentoBorde } },
        confine: true,
        formatter: (items) => {
          const lista = Array.isArray(items) ? items : [items];
          const segundo = lista[0]?.axisValue;
          const fase = segundo < 0 ? 'antes' : segundo > 0 ? 'después' : 'instante del handover';
          const filas = lista
            .filter((p) => p.data?.[1] !== null && p.data?.[1] !== undefined)
            .map((p) => `${p.marker} ${p.seriesName}: <strong>${p.data[1]}</strong>`);

          return [
            `<strong>${segundo > 0 ? '+' : ''}${segundo} s</strong> <span style="color:${TEMA.textoSuave}">(${fase})</span>`,
            filas.length
              ? filas.join('<br/>')
              : `<span style="color:${TEMA.textoSuave}">Sin medidas válidas</span>`,
          ].join('<br/>');
        },
      },
      xAxis: eje({
        type: 'value',
        name: 'segundos respecto al handover',
        nameLocation: 'middle',
        nameGap: 26,
        splitLine: { show: false },
        axisLabel: { formatter: (v) => `${v > 0 ? '+' : ''}${v}s` },
      }),
      yAxis: [
        eje({ type: 'value', name: 'dBm', scale: true }),
        eje({ type: 'value', name: 'dB', scale: true, show: hayEjeDerecho, splitLine: { show: false } }),
      ],
      series,
    };
  }, [datos, parametros]);
}

/** Etiqueta de una celda en el histograma según el identificador elegido. */
export function etiquetaCelda(celda, eje = 'celda_clave') {
  return eje === 'psc_pci' && celda.psc_pci != null ? `PCI ${celda.psc_pci}` : celda.celda_clave;
}

/** Ancho máximo, en píxeles, de los rótulos de celda antes de truncarlos con «…». */
export const ANCHO_ROTULO_CELDA = 116;

/**
 * Alto del histograma horizontal: una fila cómoda por celda, con un mínimo para que dos o tres
 * barras no queden como una franja aplastada.
 */
export function altoHistograma(nCeldas) {
  return Math.max(180, nCeldas * 26 + 48);
}

/**
 * Opción del histograma de radiobases repetidas (HU-C2-008).
 *
 * Una «visita» es un tramo de permanencia: si el terminal vuelve a la misma celda más tarde,
 * cuenta otra vez. Es lo que revela los patrones de movilidad y las zonas de solapamiento.
 *
 * **Barras horizontales.** Los identificadores de celda son largos (`WCDMA:13163:30405`); en un
 * eje X había que rotarlos 45° y leerlos torciendo la cabeza. En horizontal se leen de corrido y,
 * si aun así no caben, se truncan con «…» y el nombre completo aparece al pasar el ratón por el
 * rótulo o por la barra.
 */
export function useOpcionCeldasRepetidas({ celdas = [], eje: ejeCeldas = 'celda_clave' }) {
  return useMemo(() => {
    if (!celdas.length) return null;

    return {
      animation: false,
      grid: { left: 8, right: 36, top: 8, bottom: 30, containLabel: true },
      tooltip: {
        ...ESTILO_TOOLTIP,
        trigger: 'item',
        confine: true,
        formatter: (p) => {
          const c = celdas[p.dataIndex];
          if (!c) return '';
          return [
            `<strong>${etiquetaCelda(c, ejeCeldas)}</strong>`,
            `<div style="margin-top:4px">Visitas: <strong>${c.n_visitas}</strong></div>`,
            `<div>Mediciones: ${c.n_mediciones}</div>`,
            `<div>Tiempo acumulado: ${Math.round(c.tiempo_total_s)} s</div>`,
            c.tech ? `<div style="color:${TEMA.textoSuave}">${c.tech}</div>` : '',
          ]
            .filter(Boolean)
            .join('');
        },
      },
      xAxis: eje({
        type: 'value',
        name: 'visitas',
        nameLocation: 'middle',
        nameGap: 24,
        minInterval: 1,
      }),
      yAxis: eje({
        type: 'category',
        // La celda con más visitas arriba: se lee como un ranking.
        inverse: true,
        data: celdas.map((c) => etiquetaCelda(c, ejeCeldas)),
        splitLine: { show: false },
        axisLine: { show: false },
        axisLabel: {
          width: ANCHO_ROTULO_CELDA,
          overflow: 'truncate',
          ellipsis: '…',
          fontFamily: 'ui-monospace, "Cascadia Code", Consolas, monospace',
          fontSize: 10.5,
        },
        // Permite que el rótulo emita eventos: el componente los usa para mostrar el nombre
        // completo de una celda truncada.
        triggerEvent: true,
      }),
      series: [
        {
          type: 'bar',
          data: celdas.map((c) => c.n_visitas),
          barMaxWidth: 16,
          itemStyle: { color: TEMA.acento, borderRadius: [0, 6, 6, 0] },
          emphasis: { itemStyle: { color: TEMA.acentoFuerte } },
          label: {
            show: true,
            position: 'right',
            distance: 6,
            color: TEMA.textoSuave,
            fontSize: 10,
          },
        },
      ],
    };
  }, [celdas, ejeCeldas]);
}

/**
 * Índice de la barra cuyo rótulo del eje Y ha recibido el ratón, o `-1` si el evento no viene
 * de un rótulo. Permite abrir el tooltip de la barra al pasar por su nombre truncado.
 */
export function indiceDeRotulo(evento, celdas = [], ejeCeldas = 'celda_clave') {
  if (evento?.componentType !== 'yAxis') return -1;
  return celdas.findIndex((c) => etiquetaCelda(c, ejeCeldas) === evento.value);
}
