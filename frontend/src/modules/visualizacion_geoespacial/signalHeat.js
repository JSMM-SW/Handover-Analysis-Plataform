// Display ranges, not calibrated coverage or handover success thresholds.
export const SIGNAL_METRICS = {
  rssi: { label: 'RSSI', unit: 'dBm', high: -80, low: -100 },
  rsrq: { label: 'RSRQ', unit: 'dB', high: -10, low: -15 },
};
export const SIGNAL_COLORS = { high: '#128777', middle: '#cf9209', low: '#cf4960', missing: '#81909f' };

export function signalColor(value, metric) {
  if (value == null) return SIGNAL_COLORS.missing;
  const ranges = SIGNAL_METRICS[metric];
  return value >= ranges.high ? SIGNAL_COLORS.high : value >= ranges.low ? SIGNAL_COLORS.middle : SIGNAL_COLORS.low;
}

export function heatColor(value, metric) {
  if (value == null) return [129, 144, 159];
  const { high, low } = SIGNAL_METRICS[metric];
  const t = Math.max(0, Math.min(1, (value - low) / (high - low)));
  const stops = [[207, 73, 96], [207, 146, 9], [18, 135, 119]];
  const index = t < 0.5 ? 0 : 1;
  const fraction = index === 0 ? t * 2 : (t - 0.5) * 2;
  return stops[index].map((v, channel) => Math.round(v + (stops[index + 1][channel] - v) * fraction));
}

// Points are projected to canvas pixels. Normalize signal by kernel weight:
// repeated observations do not turn an unchanged signal into a worse color.
export function signalRaster(points, metric, width, height, radius = 18) {
  const weights = new Float32Array(width * height);
  const sums = new Float32Array(width * height);
  const opacity = new Float32Array(width * height);
  const missing = new Float32Array(width * height);
  const kernel = [];
  const edge = Math.exp(-4.5);
  for (let dy = -radius; dy <= radius; dy++) for (let dx = -radius; dx <= radius; dx++) {
    const distance = dx * dx + dy * dy;
    if (distance >= radius * radius) continue;
    kernel.push([dx, dy, (Math.exp(-4.5 * distance / (radius * radius)) - edge) / (1 - edge)]);
  }
  for (const { x, y, value } of points) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    const cx = Math.round(x), cy = Math.round(y);
    if (cx < -radius || cy < -radius || cx >= width + radius || cy >= height + radius) continue;
    for (const [dx, dy, weight] of kernel) {
      const px = cx + dx, py = cy + dy;
      if (px < 0 || py < 0 || px >= width || py >= height) continue;
      const i = py * width + px;
      if (Number.isFinite(value)) {
        sums[i] += value * weight;
        weights[i] += weight;
        opacity[i] = Math.max(opacity[i], weight);
      } else missing[i] = Math.max(missing[i], weight);
    }
  }
  const pixels = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < weights.length; i++) {
    const alpha = weights[i] ? opacity[i] : missing[i];
    if (!alpha) continue;
    const color = heatColor(weights[i] ? sums[i] / weights[i] : null, metric);
    pixels.set(color, i * 4);
    pixels[i * 4 + 3] = Math.round(220 * alpha);
  }
  return pixels;
}
