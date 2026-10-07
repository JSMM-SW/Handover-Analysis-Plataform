// /**
//  * Paleta pastel (azul, verde y blanco) del Módulo 2.
//  *
//  * Las gráficas de ECharts se dibujan en canvas y no leen variables CSS, así que los colores que
//  * necesitan viven aquí. Los mismos valores están declarados como tokens en
//  * `VisualizacionTemporalPage.css`: **si se cambia uno, se cambia en los dos sitios**.
//  *
//  * Criterios de la paleta (ver `docs/11-sistema-visual.md`):
//  * - Fondos blancos con un matiz azul muy suave.
//  * - Azul pastel para estados activos y selección; verde pastel para las acciones principales.
//  * - Nada de colores eléctricos: las series usan tonos apagados que se distinguen entre sí sin
//  *   competir con los marcadores de handover.
//  * - El texto sobre fondo claro usa siempre los tonos oscuros (`texto`, `acentoFuerte`): los
//  *   pasteles no alcanzan contraste suficiente para letra pequeña.
//  */

// export const TEMA = {
//   fondo: '#F2F7FA',
//   claro: '#F7FBFD',
//   superficie: '#FFFFFF',
//   borde: '#DCE7EF',
//   rejilla: '#EAF1F6',
//   texto: '#2E3A45',
//   textoSuave: '#5B6873', // ≥ 4,5:1 también sobre el fondo
//   textoTenue: '#97A6B2',

//   acento: '#7FB5DA', // azul pastel
//   acentoFuerte: '#2E6C9A', // azul profundo (texto de acento)
//   acentoBorde: '#BFDCEF',
//   acentoTenue: '#E5F1FA',
//   verde: '#7FCB9F', // verde pastel

//   mejora: '#3F7A4F',
//   empeora: '#A6452F',

//   // Marcadores de handover en las gráficas temporales.
//   marcadorHO: '#9A8478', // gris topo: presente en todas las curvas sin competir con ellas
//   marcadorHOSeleccionado: '#C2185B', // frambuesa: ningún parámetro RF usa este tono
// };

// /**
//  * Colores de las series de radiofrecuencia.
//  *
//  * Cinco familias de tono bien separadas en la rueda de color (naranja, verde azulado, amarillo,
//  * violeta y azul) para que dos parámetros superpuestos no se confundan. Saturación media: se
//  * distinguen con claridad sobre el fondo claro sin llegar a los colores eléctricos.
//  *
//  * RSRP y RSRQ, los parámetros realmente disponibles en el dataset, van en colores
//  * complementarios (naranja frente a verde azulado), que es la pareja más fácil de separar.
//  */
// export const COLORES_RF = {
//   rsrp_dbm: '#E0663A', // naranja terracota
//   rsrq_db: '#2A9D8F', // verde azulado
//   rssnr_db: '#E9B429', // azafrán
//   rssi_dbm: '#3A7CC3', // azul
// };

// /** Estilo común de ejes: líneas finas, rótulos en gris azulado y rejilla casi imperceptible. */
// export const ESTILO_EJE = {
//   axisLine: { lineStyle: { color: TEMA.borde } },
//   axisTick: { show: false },
//   axisLabel: { color: TEMA.textoSuave, fontSize: 11 },
//   nameTextStyle: { color: TEMA.textoTenue, fontSize: 10 },
//   splitLine: { lineStyle: { color: TEMA.rejilla, width: 1 } },
// };

// /** Tooltip de las gráficas: tarjeta clara con sombra suave, a juego con las tarjetas de la página. */
// export const ESTILO_TOOLTIP = {
//   backgroundColor: TEMA.superficie,
//   borderColor: TEMA.borde,
//   borderWidth: 1,
//   padding: [8, 12],
//   textStyle: { color: TEMA.texto, fontSize: 12 },
//   extraCssText: 'box-shadow: 0 6px 20px rgba(46,58,69,0.10); border-radius: 10px;',
// };
/**
 * Colores de las gráficas del Módulo 2.
 *
 * Las gráficas de ECharts se dibujan en canvas y no leen variables CSS, así que aquí se resuelven
 * en JavaScript las **mismas variables globales de tema** que usa el resto de la plataforma
 * (`src/index.css`): cada propiedad de `TEMA` es un getter que lee la variable en el momento en
 * que se pide, así que devuelve el color del tema activo (claro u oscuro).
 *
 * Para que una gráfica ya dibujada se actualice al alternar el tema, el hook que construye su
 * opción debe incluir `useTemaActual()` entre sus dependencias (ver `hooks/useSeriesEcharts.js`).
 *
 * Se mantienen fijos solo los colores **de datos**, que deben verse igual en ambos temas y
 * coincidir con sus leyendas: las series de radiofrecuencia (`COLORES_RF`) y los marcadores de
 * handover.
 */

import { useEffect, useState } from 'react';

/**
 * Lee el valor actual de una variable CSS global definida en `:root`.
 *
 * @param {string} nombre - nombre de la variable, con "--" (ej. "--color-borde").
 * @param {string} respaldo - color a devolver si la variable no se puede leer (ej. en pruebas
 *   con jsdom, que no aplica las hojas de estilo).
 * @returns {string} el color ya resuelto (ej. "#262b36").
 */
function leerVariable(nombre, respaldo) {
  if (typeof document === 'undefined') return respaldo;
  const valor = getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
  return valor || respaldo;
}

/**
 * Convierte un color hexadecimal (#rgb o #rrggbb) en `rgba` con la opacidad indicada.
 *
 * El canvas de ECharts no entiende `color-mix()`, así que los tonos suaves del acento se obtienen
 * aplicando transparencia al color primario: sobre fondo claro u oscuro se ven igual de suaves.
 *
 * @param {string} hex - color en formato hexadecimal.
 * @param {number} alfa - opacidad entre 0 y 1.
 * @returns {string} el color en formato `rgba(r,g,b,alfa)`, o `hex` sin cambios si no es válido.
 */
function conAlfa(hex, alfa) {
  const limpio = hex.replace('#', '');
  const completo = limpio.length === 3 ? limpio.split('').map((c) => c + c).join('') : limpio;
  if (!/^[0-9a-fA-F]{6}$/.test(completo)) return hex;
  const r = parseInt(completo.slice(0, 2), 16);
  const g = parseInt(completo.slice(2, 4), 16);
  const b = parseInt(completo.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alfa})`;
}

/**
 * Paleta de las gráficas, resuelta contra el tema activo en cada acceso.
 *
 * Los respaldos son los valores del tema claro de `src/index.css`.
 */
export const TEMA = {
  get fondo() { return leerVariable('--color-fondo', '#e7ebf1'); },
  get claro() { return leerVariable('--color-superficie-hundida', '#eef1f6'); },
  get superficie() { return leerVariable('--color-superficie', '#ffffff'); },
  get borde() { return leerVariable('--color-borde', '#d8dee6'); },
  get rejilla() { return leerVariable('--color-superficie-hundida', '#eef1f6'); },
  get texto() { return leerVariable('--color-texto', '#1f2937'); },
  get textoSuave() { return leerVariable('--color-texto-tenue', '#6b7280'); },
  get textoTenue() { return leerVariable('--color-texto-debil', '#9ca3af'); },

  get acento() { return leerVariable('--color-primario', '#2563eb'); },
  get acentoFuerte() { return leerVariable('--color-primario', '#2563eb'); },
  get acentoBorde() { return conAlfa(this.acento, 0.35); },
  get acentoTenue() { return conAlfa(this.acento, 0.12); },
  get verde() { return leerVariable('--color-exito', '#16a34a'); },

  get mejora() { return leerVariable('--color-exito', '#16a34a'); },
  get empeora() { return leerVariable('--color-error', '#dc2626'); },

  // Marcadores de handover en las gráficas temporales: colores de dato, iguales en ambos temas.
  marcadorHO: '#9A8478', // gris topo: presente en todas las curvas sin competir con ellas
  marcadorHOSeleccionado: '#C2185B', // frambuesa: ningún parámetro RF usa este tono
};

/**
 * Colores de las series de radiofrecuencia.
 *
 * Cinco familias de tono bien separadas en la rueda de color (naranja, verde azulado, amarillo,
 * violeta y azul) para que dos parámetros superpuestos no se confundan. Saturación media: se
 * distinguen con claridad sobre fondo claro y oscuro sin llegar a los colores eléctricos.
 *
 * RSRP y RSRQ, los parámetros realmente disponibles en el dataset, van en colores
 * complementarios (naranja frente a verde azulado), que es la pareja más fácil de separar.
 */
export const COLORES_RF = {
  rsrp_dbm: '#E0663A', // naranja terracota
  rsrq_db: '#2A9D8F', // verde azulado
  rssnr_db: '#E9B429', // azafrán
  rssi_dbm: '#3A7CC3', // azul
};

/**
 * Estilo común de ejes: líneas finas, rótulos en el gris tenue del tema y rejilla discreta.
 * Cada sub-objeto es un getter para que se resuelva con el tema activo al construir la opción.
 */
export const ESTILO_EJE = {
  get axisLine() { return { lineStyle: { color: TEMA.borde } }; },
  axisTick: { show: false },
  get axisLabel() { return { color: TEMA.textoSuave, fontSize: 11 }; },
  get nameTextStyle() { return { color: TEMA.textoTenue, fontSize: 10 }; },
  get splitLine() { return { lineStyle: { color: TEMA.rejilla, width: 1 } }; },
};

/**
 * Tooltip de las gráficas: misma superficie, borde y texto que las tarjetas de la página.
 * Las propiedades de color son getters para que sigan el tema activo.
 */
export const ESTILO_TOOLTIP = {
  get backgroundColor() { return TEMA.superficie; },
  get borderColor() { return TEMA.borde; },
  borderWidth: 1,
  padding: [8, 12],
  get textStyle() { return { color: TEMA.texto, fontSize: 12 }; },
  extraCssText: 'box-shadow: 0 6px 20px rgba(0,0,0,0.18); border-radius: 8px;',
};

/**
 * Devuelve el tema activo (`'claro'` u `'oscuro'`) y provoca un nuevo render cada vez que el
 * usuario lo alterna.
 *
 * App.jsx guarda el tema en el atributo `data-tema` de <html>; un MutationObserver detecta el
 * cambio. Los hooks que construyen opciones de ECharts lo incluyen en las dependencias de su
 * `useMemo` para volver a leer `TEMA` con los colores nuevos.
 *
 * @returns {string} `'claro'` u `'oscuro'`.
 */
export function useTemaActual() {
  const [tema, setTema] = useState(() =>
    typeof document === 'undefined' ? 'claro' : document.documentElement.dataset.tema ?? 'claro',
  );

  useEffect(() => {
    const raiz = document.documentElement;
    const observador = new MutationObserver(() => setTema(raiz.dataset.tema ?? 'claro'));
    observador.observe(raiz, { attributes: true, attributeFilter: ['data-tema'] });
    return () => observador.disconnect();
  }, []);

  return tema;
}
