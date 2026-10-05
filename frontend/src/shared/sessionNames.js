// The filename's session number is a display label, never a database/filter key.
export function sessionNumber(row = {}) {
  // Temporal responses include the old label before the original filename.
  const names = row.filename ? [row.filename] : (row.sesion_nombre ?? '').split(' · ').reverse();
  for (const name of names) {
    const basename = name.split(/[\\/]/).pop().trim();
    const match = basename.match(/^(?:session|sesi[oó]n)[\s_-]+(\d+)(?=[\s_.-]|$)/i);
    if (match) return match[1].replace(/^0+(?=\d)/, '');
  }
  return null;
}

export function sessionName(row = {}) {
  const number = sessionNumber(row);
  if (number !== null) return `Sesión ${number}`;
  if (row.sesion_nombre) return row.sesion_nombre;
  return `Sesión ${row.sesion_label ?? row.execution_id ?? row.sesion_id ?? 'sin identificar'}`;
}

export function sessionExportLabel(row = {}) {
  return sessionNumber(row) ?? row.sesion_label ?? row.execution_id;
}
