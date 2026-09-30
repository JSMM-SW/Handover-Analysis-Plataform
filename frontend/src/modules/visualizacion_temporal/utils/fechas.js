/**
 * Conversión entre lo que teclea el usuario y lo que entiende el backend.
 *
 * El problema que resuelve este archivo
 * -------------------------------------
 * El usuario piensa en **hora local** (ve «08:01:30» en la tabla). El backend guarda y compara
 * todo en **UTC** (`timestamptz`), y el dataset de referencia está a las 13:00 UTC porque
 * Ecuador es UTC−5.
 *
 * Si se envía la fecha tal cual sale de un `<input type="date">` —una cadena sin zona— el backend
 * la interpreta como UTC y el filtro queda desplazado cinco horas: el usuario elige las 08:00,
 * se consulta a las 08:00 UTC (03:00 locales) y no aparece nada. Aquí se hace la conversión
 * explícita en los dos sentidos.
 */

/**
 * Combina la fecha y la hora que teclea el usuario en un instante ISO con zona.
 *
 * @param {string|null} fecha  'AAAA-MM-DD' del `<input type="date">`
 * @param {string|null} hora   'HH:MM' del `<input type="time">`; por defecto el inicio del día
 * @param {'inicio'|'fin'} extremo  Sin hora, `inicio` toma 00:00:00 y `fin` toma 23:59:59
 * @returns {string|null} instante ISO-8601 en UTC, o `null` si no hay fecha
 */
export function aInstanteUTC(fecha, hora, extremo = 'inicio') {
  if (!fecha) return null;

  const [anio, mes, dia] = fecha.split('-').map(Number);
  const [h, m] = (hora || (extremo === 'fin' ? '23:59' : '00:00')).split(':').map(Number);
  const segundos = !hora && extremo === 'fin' ? 59 : 0;

  // El constructor con componentes interpreta la hora en la zona del navegador, que es
  // justamente la que el usuario tiene en la cabeza.
  return new Date(anio, mes - 1, dia, h, m, segundos).toISOString();
}

/** De un instante ISO a la fecha local 'AAAA-MM-DD' que espera un `<input type="date">`. */
export function aFechaLocal(iso) {
  if (!iso) return '';

  const fecha = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return `${fecha.getFullYear()}-${pad(fecha.getMonth() + 1)}-${pad(fecha.getDate())}`;
}

/** De un instante ISO a la hora local 'HH:MM' que espera un `<input type="time">`. */
export function aHoraLocal(iso) {
  if (!iso) return '';

  const fecha = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(fecha.getHours())}:${pad(fecha.getMinutes())}`;
}

/** Texto corto y legible de un instante, para los chips de filtros activos. */
export function textoBreve(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('es-EC', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

/** Nombre de la zona horaria del navegador, para poder decírselo al usuario. */
export function zonaHoraria() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'hora local';
  } catch {
    return 'hora local';
  }
}

/** Solo la hora local 'HH:MM:SS', para la lista visual de eventos. */
export function horaCorta(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString('es-EC', { hour12: false });
}

/** Día y mes abreviado ('01 jul'), para acompañar a la hora sin repetir el año en cada fila. */
export function fechaCorta(iso) {
  if (!iso) return '';
  return new Date(iso)
    .toLocaleDateString('es-EC', { day: '2-digit', month: 'short' })
    .replace('.', '');
}

/** Solo la fecha local 'dd/mm/aaaa', para los chips de filtros de día completo. */
export function textoFecha(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('es-EC', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}
