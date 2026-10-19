import { expect, it } from 'vitest';
import { heatColor, signalRaster } from './signalHeat';

it('weights aggregated signal cells by the valid measurement count', () => {
  const pixels = signalRaster([
    { x: 20, y: 20, value: -110, weight: 1 },
    { x: 20, y: 20, value: -80, weight: 9 },
  ], 'rssi', 40, 40);
  const center = (20 * 40 + 20) * 4;
  expect([...pixels.slice(center, center + 3)]).toEqual(heatColor(-83, 'rssi'));
  expect(pixels[center + 3]).toBeGreaterThan(0);
});

it('keeps missing signal cells distinguishable without treating null as zero', () => {
  const pixels = signalRaster([{ x: 20, y: 20, value: null, weight: 0 }], 'rssnr', 40, 40);
  const center = (20 * 40 + 20) * 4;
  expect([...pixels.slice(center, center + 3)]).toEqual(heatColor(null, 'rssnr'));
});

it('includes all 100000 coincident observations without a geographic group average', () => {
  const points = Array.from({ length: 100000 }, (_, i) => ({ x: 20, y: 20, value: i < 25000 ? -110 : -70 }));
  const pixels = signalRaster(points, 'rssi', 40, 40);
  const center = (20 * 40 + 20) * 4;
  expect([...pixels.slice(center, center + 3)]).toEqual(heatColor(-80, 'rssi'));
});
