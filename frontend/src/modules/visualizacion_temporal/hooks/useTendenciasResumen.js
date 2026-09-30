/**
 * Tendencias de las tarjetas de resumen (Capa 2) — micro-visualizaciones de HU-C2-007.
 *
 * Cada tarjeta lleva un *sparkline* que resume de un vistazo cómo evolucionó su indicador a lo
 * largo del recorrido. No se pide nada nuevo al backend: se reutilizan las consultas de handovers
 * y de tramos de celda **con la misma query key que usan las gráficas**, así que TanStack Query
 * las sirve desde caché y no hay peticiones extra.
 *
 * Todas las series se reparten en `N_INTERVALOS` intervalos iguales entre el inicio y el fin del
 * rango filtrado, de modo que los sparklines de distintas tarjetas son comparables entre sí.
 *
 * Las funciones puras se exportan aparte para probarlas sin renderizar.
 */

import { useMemo } from 'react';

import { useHandovers, useResumen, useSeriesCeldas } from './useDatosVT.js';

export const N_INTERVALOS = 16;

const ms = (iso) => new Date(iso).getTime();

/**
 * Límites temporales del rango: los del resumen si los hay; si no, los de los tramos.
 *
 * @returns {[number, number]|null} par de milisegundos, o `null` si no se puede acotar
 */
export function rangoTemporal({ inicio, fin, tramos = [] }) {
  const a = inicio ? ms(inicio) : tramos.length ? ms(tramos[0].inicio) : NaN;
  const b = fin ? ms(fin) : tramos.length ? ms(tramos[tramos.length - 1].fin) : NaN;

  if (!Number.isFinite(a) || !Number.isFinite(b) || b <= a) return null;
  return [a, b];
}

/** Índice del intervalo en que cae un instante (los extremos se asignan al primero y al último). */
function intervaloDe(instante, [a, b], n) {
  const i = Math.floor(((instante - a) / (b - a)) * n);
  return Math.min(n - 1, Math.max(0, i));
}

/** Handovers ocurridos en cada intervalo. */
export function handoversPorIntervalo(handovers, rango, n = N_INTERVALOS) {
  if (!rango) return null;

  const cuentas = new Array(n).fill(0);
  handovers.forEach((ho) => {
    cuentas[intervaloDe(ms(ho.timestamp_evento), rango, n)] += 1;
  });
  return cuentas;
}

/**
 * Tasa acumulada de handovers por minuto al final de cada intervalo.
 *
 * Se usa la tasa **acumulada** y no la de cada intervalo porque esta última dibujaría la misma
 * forma que el sparkline de handovers. La acumulada muestra otra cosa: si el ritmo de traspasos
 * se estabiliza o si se concentra en una parte del recorrido.
 */
export function tasaAcumuladaPorIntervalo(handovers, rango, n = N_INTERVALOS) {
  const cuentas = handoversPorIntervalo(handovers, rango, n);
  if (!cuentas) return null;

  const minutosPorIntervalo = (rango[1] - rango[0]) / n / 60000;
  let acumulado = 0;

  return cuentas.map((cuenta, i) => {
    acumulado += cuenta;
    return acumulado / (minutosPorIntervalo * (i + 1));
  });
}

/** Radiobases distintas vistas hasta el final de cada intervalo (curva creciente). */
export function radiobasesAcumuladas(tramos, rango, n = N_INTERVALOS) {
  if (!rango || !tramos.length) return null;

  const vistas = new Set();
  const resultado = [];
  let indice = 0;
  const ordenados = [...tramos].sort((x, y) => ms(x.inicio) - ms(y.inicio));

  for (let i = 0; i < n; i += 1) {
    const finIntervalo = rango[0] + ((rango[1] - rango[0]) * (i + 1)) / n;
    while (indice < ordenados.length && ms(ordenados[indice].inicio) <= finIntervalo) {
      vistas.add(ordenados[indice].celda_clave);
      indice += 1;
    }
    resultado.push(vistas.size);
  }
  return resultado;
}

/**
 * Mediciones en cada intervalo.
 *
 * Los tramos traen cuántas mediciones contienen pero no cuándo se tomó cada una, así que se
 * reparten en proporción al solape del tramo con cada intervalo. Es una aproximación suficiente
 * para una micro-visualización y deja ver lo importante: **los huecos de captura** caen a cero.
 */
export function medicionesPorIntervalo(tramos, rango, n = N_INTERVALOS) {
  if (!rango || !tramos.length) return null;

  const [a, b] = rango;
  const paso = (b - a) / n;
  const cuentas = new Array(n).fill(0);

  tramos.forEach((tramo) => {
    const ti = ms(tramo.inicio);
    const tf = ms(tramo.fin);
    const duracion = tf - ti;

    if (duracion <= 0) {
      cuentas[intervaloDe(ti, rango, n)] += tramo.n_mediciones;
      return;
    }

    for (let i = 0; i < n; i += 1) {
      const solape = Math.min(tf, a + paso * (i + 1)) - Math.max(ti, a + paso * i);
      if (solape > 0) cuentas[i] += (tramo.n_mediciones * solape) / duracion;
    }
  });
  return cuentas;
}

/**
 * Trazo SVG de un sparkline.
 *
 * @param {number[]} valores
 * @param {{ancho?: number, alto?: number, margen?: number}} [dimensiones]
 * @returns {{linea: string, area: string, ultimo: {x: number, y: number}}|null}
 *   `null` si no hay al menos dos puntos: una línea de un punto no dice nada.
 */
export function construirTrazoSparkline(valores, { ancho = 100, alto = 28, margen = 2 } = {}) {
  if (!Array.isArray(valores) || valores.length < 2) return null;

  const minimo = Math.min(...valores);
  const maximo = Math.max(...valores);
  const rangoY = maximo - minimo || 1; // serie plana: se dibuja centrada, no se divide por cero
  const plana = maximo === minimo;

  const puntos = valores.map((valor, i) => {
    const x = (i / (valores.length - 1)) * ancho;
    const y = plana
      ? alto / 2
      : margen + (1 - (valor - minimo) / rangoY) * (alto - margen * 2);
    return { x: Number(x.toFixed(2)), y: Number(y.toFixed(2)) };
  });

  const linea = puntos.map((p, i) => `${i ? 'L' : 'M'}${p.x} ${p.y}`).join(' ');
  const area = `${linea} L${ancho} ${alto} L0 ${alto} Z`;

  return { linea, area, ultimo: puntos[puntos.length - 1] };
}

/**
 * Barras de un sparkline de recuento (p. ej. handovers por intervalo).
 *
 * Para recuentos se usan barras y no línea: una línea entre «2 handovers» y «0 handovers»
 * sugeriría valores intermedios que no existen.
 *
 * @returns {{x: number, y: number, ancho: number, alto: number}[]|null}
 */
export function construirBarrasSparkline(valores, { ancho = 100, alto = 28, hueco = 1.2 } = {}) {
  if (!Array.isArray(valores) || !valores.length) return null;

  const maximo = Math.max(...valores);
  const paso = ancho / valores.length;

  return valores.map((valor, i) => {
    // Un intervalo sin eventos deja un trazo mínimo: así se ve que hay intervalo, pero vacío.
    const altura = maximo > 0 ? Math.max(1, (valor / maximo) * alto) : 1;
    return {
      x: Number((i * paso + hueco / 2).toFixed(2)),
      y: Number((alto - altura).toFixed(2)),
      ancho: Number(Math.max(0.5, paso - hueco).toFixed(2)),
      alto: Number(altura.toFixed(2)),
    };
  });
}

/**
 * Series de tendencia para las tarjetas de resumen.
 *
 * Devuelve `null` en cada serie que no se pueda calcular todavía (datos cargando o rango sin
 * duración); la tarjeta simplemente no dibuja su sparkline.
 */
export function useTendenciasResumen() {
  const resumen = useResumen();
  const handovers = useHandovers({ pageSize: 500 });
  const celdas = useSeriesCeldas();

  return useMemo(() => {
    const eventos = handovers.data?.items ?? [];
    const tramos = celdas.data?.tramos ?? [];
    const rango = rangoTemporal({
      inicio: resumen.data?.ventana_inicio,
      fin: resumen.data?.ventana_fin,
      tramos,
    });

    return {
      handovers: handovers.data?.items ? handoversPorIntervalo(eventos, rango) : null,
      tasa: handovers.data?.items ? tasaAcumuladaPorIntervalo(eventos, rango) : null,
      radiobases: radiobasesAcumuladas(tramos, rango),
      mediciones: medicionesPorIntervalo(tramos, rango),
    };
  }, [resumen.data, handovers.data, celdas.data]);
}
