// El nombre de una sesión sale SOLO de etl_execution.sesion_label: el número que
// asigna la base al confirmar la carga (consecutivo, sin huecos). Nunca del
// nombre del archivo: "Session_31_20240308_171157.csv" es "Sesión N", no "Sesión 31".
// El nombre del archivo se conserva en filename/archivo_origen y solo sirve
// para detectar duplicados.
export const SESSION_PENDING = 'Sesión pendiente';

export function sessionNumber(row = {}) {
  if (row.sesion_label !== null && row.sesion_label !== undefined && row.sesion_label !== '') {
    return String(row.sesion_label);
  }
  // Las respuestas de Temporal no traen sesion_label suelto, sino
  // sesion_nombre = "Sesión <sesion_label> · <archivo> · <hoja>": el número es
  // el del primer segmento (el que escribió el backend), no el del archivo.
  const label = String(row.sesion_nombre ?? '').split(' · ')[0].match(/^Sesi[oó]n (\d+)$/i);
  return label ? label[1] : null;
}

// Sin sesion_label todavía (processing, failed, cancelled) no se inventa un
// número: se muestra el nombre del archivo o "Sesión pendiente".
export function sessionName(row = {}) {
  const number = sessionNumber(row);
  if (number !== null) return `Sesión ${number}`;
  return row.filename || row.sesion_nombre || SESSION_PENDING;
}

export function sessionExportLabel(row = {}) {
  return sessionNumber(row) ?? 'pendiente';
}
