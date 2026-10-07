/**
 * Paleta pastel (azul, verde y blanco) del Módulo 2.
 *
 * Las gráficas de ECharts se dibujan en canvas y no leen variables CSS, así que los colores que
 * necesitan viven aquí. Los mismos valores están declarados como tokens en
 * `VisualizacionTemporalPage.css`: **si se cambia uno, se cambia en los dos sitios**.
 *
 * Criterios de la paleta (ver `docs/11-sistema-visual.md`):
 * - Fondos blancos con un matiz azul muy suave.
 * - Azul pastel para estados activos y selección; verde pastel para las acciones principales.
 * - Nada de colores eléctricos: las series usan tonos apagados que se distinguen entre sí sin
 *   competir con los marcadores de handover.
 * - El texto sobre fondo claro usa siempre los tonos oscuros (`texto`, `acentoFuerte`): los
 *   pasteles no alcanzan contraste suficiente para letra pequeña.
 */

export const TEMA = {
  fondo: '#F2F7FA',
  claro: '#F7FBFD',
  superficie: '#FFFFFF',
  borde: '#DCE7EF',
  rejilla: '#EAF1F6',
  texto: '#2E3A45',
  textoSuave: '#5B6873', // ≥ 4,5:1 también sobre el fondo
  textoTenue: '#97A6B2',

  acento: '#7FB5DA', // azul pastel
  acentoFuerte: '#2E6C9A', // azul profundo (texto de acento)
  acentoBorde: '#BFDCEF',
  acentoTenue: '#E5F1FA',
  verde: '#7FCB9F', // verde pastel

  mejora: '#3F7A4F',
  empeora: '#A6452F',

  // Marcadores de handover en las gráficas temporales.
  marcadorHO: '#9A8478', // gris topo: presente en todas las curvas sin competir con ellas
  marcadorHOSeleccionado: '#C2185B', // frambuesa: ningún parámetro RF usa este tono
};

/**
 * Colores de las series de radiofrecuencia.
 *
 * Cinco familias de tono bien separadas en la rueda de color (naranja, verde azulado, amarillo,
 * violeta y azul) para que dos parámetros superpuestos no se confundan. Saturación media: se
 * distinguen con claridad sobre el fondo claro sin llegar a los colores eléctricos.
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

/** Estilo común de ejes: líneas finas, rótulos en gris azulado y rejilla casi imperceptible. */
export const ESTILO_EJE = {
  axisLine: { lineStyle: { color: TEMA.borde } },
  axisTick: { show: false },
  axisLabel: { color: TEMA.textoSuave, fontSize: 11 },
  nameTextStyle: { color: TEMA.textoTenue, fontSize: 10 },
  splitLine: { lineStyle: { color: TEMA.rejilla, width: 1 } },
};

/** Tooltip de las gráficas: tarjeta clara con sombra suave, a juego con las tarjetas de la página. */
export const ESTILO_TOOLTIP = {
  backgroundColor: TEMA.superficie,
  borderColor: TEMA.borde,
  borderWidth: 1,
  padding: [8, 12],
  textStyle: { color: TEMA.texto, fontSize: 12 },
  extraCssText: 'box-shadow: 0 6px 20px rgba(46,58,69,0.10); border-radius: 10px;',
};
