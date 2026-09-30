import { formatDate, formatHour, technologyName } from './formatters';

function appendFields(container, fields) {
  for (const [label, value] of fields) {
    const row = document.createElement('div');
    row.textContent = `${label}: ${value}`;
    container.append(row);
  }
}

export function handoverTooltip(point, metric = null) {
  const content = document.createElement('div');
  content.className = 'geo-handover-tooltip';
  const title = document.createElement('strong');
  title.textContent = `Handover ${point.celda_origen} → ${point.cell_id}`;
  content.append(title);
  appendFields(content, [
    ['Fecha', formatDate(point.timestamp_medicion)],
    ['Hora', formatHour(point.timestamp_medicion)],
    ['RSSI', point.rssi == null ? 'Sin dato' : `${point.rssi} dBm`],
    ['RSRQ', point.rsrq == null ? 'Sin dato' : `${point.rsrq} dB`],
    ['RSSNR', point.rssnr == null ? 'Sin dato' : String(point.rssnr)],
  ].filter(([label]) => !metric || !['RSSI', 'RSRQ', 'RSSNR'].includes(label) || label === metric.toUpperCase()));
  return content;
}

export function radioBasePopup(estimates, executions) {
  const content = document.createElement('div');
  content.className = 'geo-radio-popup';
  for (const station of estimates) {
    const section = document.createElement('section');
    const heading = document.createElement('strong');
    heading.textContent = 'Radio base estimada';
    section.append(heading);
    const session = executions?.find((row) => row.execution_id === station.execution_id);
    appendFields(section, [
      ['Sesión', session?.sesion_label ?? station.execution_id],
      ['Nodo', station.node_id], ['Celda', station.cell_id],
      ['Tecnología', technologyName(station.tecnologia)],
      ['Coordenadas estimadas', `${station.latitud}, ${station.longitud}`],
    ]);
    const note = document.createElement('p');
    note.textContent = 'Ubicación aproximada calculada a partir de las mediciones.';
    section.append(note);
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Detalles de la estimación';
    details.append(summary);
    appendFields(details, [
      [station.tecnologia === 1 ? 'PCI' : 'PSC', station.psc_pci?.length ? station.psc_pci.join(', ') : 'Sin dato'],
      ['Canal de frecuencia (ARFCN)', station.earfcn],
      ['Muestras válidas sin repetir', station.mediciones_validas],
      ['Posiciones utilizadas', `${station.posiciones_utilizadas} de ${station.posiciones_disponibles}`],
      ['RSSI máximo de posiciones', `${station.rssi_max} dBm`],
      ['Dispersión de posiciones', `${station.dispersion_m} m (no es el error de ubicación)`],
    ]);
    section.append(details);
    content.append(section);
  }
  return content;
}

