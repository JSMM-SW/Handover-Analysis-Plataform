import { test, expect } from '@playwright/test';
import { signalRaster, heatColor } from '../src/modules/visualizacion_geoespacial/signalHeat';

const pixel = (pixels, x, y) => [...pixels.slice((y * 60 + x) * 4, (y * 60 + x) * 4 + 4)];
test('signal heat has soft circular edges and keeps isolated event values', () => {
  const raster = signalRaster([{ x: 30, y: 30, value: -75 }], 'rssi', 60, 60);
  expect(pixel(raster, 30, 30).slice(0, 3)).toEqual(heatColor(-75, 'rssi'));
  expect(pixel(raster, 40, 30)[3]).toBeLessThan(pixel(raster, 30, 30)[3]);
  expect(pixel(raster, 48, 30)[3]).toBe(0);
  expect(pixel(raster, 47, 47)[3]).toBe(0);
});

test('overlaps average by weight without treating density or missing values as worse signal', () => {
  const points = [-70, -90, null].map((value) => ({ x: 30, y: 30, value }));
  const original = signalRaster(points, 'rssi', 60, 60);
  expect(pixel(original, 30, 30).slice(0, 3)).toEqual(heatColor(-80, 'rssi'));
  expect(pixel(signalRaster([...points, ...points], 'rssi', 60, 60), 30, 30)).toEqual(pixel(original, 30, 30));
  expect(pixel(signalRaster([{ x: 30, y: 30, value: null }], 'rsrq', 60, 60), 30, 30).slice(0, 3)).toEqual(heatColor(null, 'rsrq'));
  expect(heatColor(-18, 'rsrq')).toEqual([207, 73, 96]);
});
