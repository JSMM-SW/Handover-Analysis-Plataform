/**
 * Formato de las cifras de las tarjetas de resumen (funciones puras).
 *
 * Cómo se calcula cada cifra en el backend: `docs/12-calculos-del-modulo.md`.
 */

/** Duración legible: '1 h 5 min', '21 min' o '40 s'. */
export function formatearDuracion(segundos) {
  if (segundos == null) return '—';

  const horas = Math.floor(segundos / 3600);
  const minutos = Math.round((segundos % 3600) / 60);

  if (horas) return `${horas} h ${minutos} min`;
  if (minutos) return `${minutos} min`;
  return `${Math.round(segundos)} s`;
}

/**
 * Desglose de los handovers por tecnología: «LTE: 37 · LTE→WCDMA: 2».
 *
 * Un nombre solo es un traspaso dentro de esa tecnología; «A→B» es un traspaso de la tecnología A
 * (origen) a la B (destino). Los números suman el total de handovers.
 *
 * @param {Record<string, number>} [porTecnologia]  `por_tecnologia` de `GET /resumen`
 */
export function desgloseTecnologia(porTecnologia = {}) {
  return Object.entries(porTecnologia)
    .sort((a, b) => b[1] - a[1])
    // «LTE->WCDMA» se muestra con flecha tipográfica: se lee mejor y no se parte en dos líneas.
    .map(([nombre, total]) => `${nombre.replace('->', '→')}: ${total}`)
    .join(' · ');
}
