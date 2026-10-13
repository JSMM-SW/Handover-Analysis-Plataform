import { aHora, aMinutos, diasEnRango } from '../visualizacion_temporal/utils/disponibilidad';

// Start at the first capture hour and offer five-minute steps through its end.
export function availableHours(days, from, to) {
  let first = Infinity;
  let last = -Infinity;
  for (const day of diasEnRango(days, from, to)) {
    for (const range of day.franjas ?? []) {
      first = Math.min(first, aMinutos(range.inicio));
      last = Math.max(last, aMinutos(range.fin));
    }
  }
  if (!Number.isFinite(first)) return { inicios: [], fines: [] };
  const minutes = [];
  const start = Math.floor(first / 60) * 60;
  const end = Math.min(1439, Math.ceil(last / 5) * 5);
  for (let minute = start; minute <= end; minute += 5) minutes.push(minute);
  // Include the final minute when rounding would otherwise cross midnight.
  if (end === 1439) minutes.push(end);
  const options = minutes.map((minute) => ({
    valor: aHora(minute), etiqueta: aHora(minute),
  }));
  return { inicios: options, fines: options };
}
