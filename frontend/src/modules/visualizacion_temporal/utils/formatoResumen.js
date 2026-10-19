/**
 * Formato de las cifras de las tarjetas de resumen (funciones puras).
 *
 * Cómo se calcula cada cifra en el backend: `docs/12-calculos-del-modulo.md`.
 */

/** Número de mediciones con separador de miles: '86.398 mediciones', '1 medición'. */
export function formatearMediciones(total) {
  const n = total ?? 0;
  return `${n.toLocaleString('es-EC')} ${n === 1 ? 'medición' : 'mediciones'}`;
}

/** Duración legible: '1 h 5 min', '24 h', '21 min' o '20 s'. */
export function formatearDuracion(segundos) {
  if (segundos == null) return '—';

  // Se redondea el total de minutos antes de separar las horas: redondear solo el resto daba
  // «23 h 60 min» con una sesión de 23:59:30.
  const totalMinutos = Math.round(segundos / 60);
  const horas = Math.floor(totalMinutos / 60);
  const minutos = totalMinutos % 60;

  if (horas) return minutos ? `${horas} h ${minutos} min` : `${horas} h`;
  if (minutos) return `${minutos} min`;
  return `${Math.round(segundos)} s`;
}

/**
 * Handovers por tecnología de origen y de destino, para el popover de la tarjeta «Handovers».
 *
 * `por_tecnologia` trae una clave por transición: un nombre solo («LTE») es un traspaso dentro de
 * esa tecnología, que aquí se escribe completo, «LTE → LTE»; «A->B» es uno de la tecnología A
 * (origen) a la B (destino), un Inter-RAT. Así todas las filas se leen igual: de dónde a dónde.
 *
 * De más a menos; a igualdad, por nombre. Un evento sin tecnología sale como «Sin dato».
 *
 * @param {Record<string, number>} [porTecnologia]  `por_tecnologia` de `GET /resumen`
 * @returns {{clave: string, origen: string, destino: string|null, total: number}[]}
 */
export function desgloseTecnologia(porTecnologia = {}) {
  return Object.entries(porTecnologia ?? {})
    .filter(([, total]) => total > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([clave, total]) => {
      if (clave === 'desconocida') return { clave, origen: 'Sin dato', destino: null, total };
      const [origen, destino = origen] = clave.split('->');
      return { clave, origen, destino, total };
    });
}
