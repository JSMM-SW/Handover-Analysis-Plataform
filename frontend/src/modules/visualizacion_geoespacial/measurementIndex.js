// The compact API sample is [lat, lon, RSSI, RSRP, RSRQ, RSSNR, id, time, cell].
export function measurementFromSample(sample) {
  if (!Array.isArray(sample)) return sample;
  const [latitud, longitud, rssi, rsrp, rsrq, rssnr, id_registro, timestamp_medicion, cell_id] = sample;
  return { latitud, longitud, rssi, rsrp, rsrq, rssnr, id_registro, timestamp_medicion, cell_id };
}

export function measurementIndex(points, cellSize = 16) {
  const cells = new Map();
  const coordinates = new Set();
  for (const [order, point] of points.entries()) {
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) continue;
    // Coincident samples all contribute to heat; hover consistently selects
    // the first original sample at that exact position, never a group average.
    const position = `${point.x},${point.y}`;
    if (coordinates.has(position)) continue;
    coordinates.add(position);
    const key = `${Math.floor(point.x / cellSize)},${Math.floor(point.y / cellSize)}`;
    if (!cells.has(key)) cells.set(key, []);
    cells.get(key).push({ ...point, order });
  }
  return {
    nearest(x, y, radius = 8) {
      let best = null;
      let distance = radius * radius;
      for (let cy = Math.floor((y - radius) / cellSize); cy <= Math.floor((y + radius) / cellSize); cy++) {
        for (let cx = Math.floor((x - radius) / cellSize); cx <= Math.floor((x + radius) / cellSize); cx++) {
          for (const point of cells.get(`${cx},${cy}`) ?? []) {
            const squared = (point.x - x) ** 2 + (point.y - y) ** 2;
            if (squared < distance || squared === distance && (!best || point.order < best.order)) {
              best = point;
              distance = squared;
            }
          }
        }
      }
      return best?.sample ?? null;
    },
  };
}
