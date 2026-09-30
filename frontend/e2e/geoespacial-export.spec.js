import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { Buffer } from 'node:buffer';

async function prepare(page, { brokenTiles = false, empty = false } = {}) {
  const tile = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 256;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = 'rgb(220,225,230)';
    ctx.fillRect(0, 0, 256, 256);
    return canvas.toDataURL().split(',')[1];
  });
  await page.route('https://tile.openstreetmap.org/**', (route) => brokenTiles ? route.abort() : route.fulfill({
    contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: Buffer.from(tile, 'base64'),
  }));
  const points = [0, 1, 2].map((n) => ({ id_registro: String(n), latitud: -0.2 + n * 0.001,
    longitud: -78.5 + n * 0.001, rssi: -75, rsrq: -18, cell_id: 10, node_id: 100, timestamp_medicion: '2026-05-05T13:00:00Z' }));
  await page.route('**/api/v1/geoespacial/**', (route) => route.fulfill({ json:
    new URL(route.request().url()).pathname.endsWith('/ejecuciones') ? [
      { execution_id: 'first', sesion_label: 14, records_valid: 3 },
      { execution_id: 'second', sesion_label: 15, records_valid: 3 },
    ] : { mediciones: empty ? [] : points, total: empty ? 0 : 3, handovers: empty ? [] : [points[1]], total_handovers: empty ? 0 : 1,
      tramos: empty ? [] : [['0', '1', '2']], radios_base: empty ? [] : [{ ...points[0], execution_id: 'first', tecnologia: 1 }], advertencias: [] },
  }));
  await page.goto('/geoespacial');
  await page.getByRole('button', { name: /Selecciona las sesiones/ }).click();
  await page.locator('.geo-session-option input').first().check();
  await page.getByRole('button', { name: 'Analizar sesiones', exact: true }).click();
  await expect(page.getByText('Datos analizados').locator('..').locator('strong')).toHaveText(empty ? '0' : '3');
}

async function capture(page, testInfo, name) {
  const pending = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Descargar mapa' }).click();
  const download = await pending;
  expect(download.suggestedFilename()).toMatch(name);
  const path = testInfo.outputPath(download.suggestedFilename());
  await download.saveAs(path);
  const png = await readFile(path);
  expect(png.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
  return page.evaluate(async (base64) => {
    const image = new Image();
    image.src = `data:image/png;base64,${base64}`;
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = image.width; canvas.height = image.height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(image, 0, 0);
    // Count actual map pixels, excluding the legend at the bottom.
    const pixels = ctx.getImageData(0, 0, image.width, 1000).data;
    const counts = { tile: 0, purple: 0, green: 0, heat: 0, red: 0 };
    for (let i = 0; i < pixels.length; i += 4) {
      const [r, g, b] = pixels.slice(i, i + 3);
      if (r === 220 && g === 225 && b === 230) counts.tile++;
      if (Math.abs(r - 121) < 5 && Math.abs(g - 83) < 5 && Math.abs(b - 168) < 5) counts.purple++;
      if (r < 60 && g > 100 && g < 170 && b > 80 && b < 160) counts.green++;
      if (b > r + 30 && b > g + 15) counts.heat++;
      if (r > g + 50 && r > b + 40) counts.red++;
    }
    return { ...counts, width: image.width, height: image.height };
  }, png.toString('base64'));
}

test('downloads PNG with visible layers, legend, and session filename in both tabs', async ({ page }, testInfo) => {
  await prepare(page);
  await page.getByRole('checkbox', { name: 'Radios Base', exact: true }).check();
  const routes = await capture(page, testInfo, /^mapa_handovers_sesion_14_.*\.png$/);
  expect(routes.tile).toBeGreaterThan(100000);
  expect(routes.purple).toBeGreaterThan(20);
  expect(routes.green).toBeGreaterThan(20);
  expect(routes.height).toBeGreaterThan(1080);
  await page.getByRole('checkbox', { name: 'Handovers', exact: true }).uncheck();
  await page.getByRole('checkbox', { name: 'Trayectoria', exact: true }).uncheck();
  await page.getByRole('tab', { name: 'Mapa de calor', exact: true }).click();
  // Export after changing the viewport, not only at the initial fitBounds.
  await page.locator('.leaflet-control-zoom-out').click();
  const map = await page.locator('.geo-map').boundingBox();
  await page.mouse.move(map.x + map.width / 2, map.y + map.height / 2);
  await page.mouse.down();
  await page.mouse.move(map.x + map.width / 2 + 40, map.y + map.height / 2 + 30, { steps: 8 });
  await page.mouse.up();
  const heat = await capture(page, testInfo, /^mapa_calor_sesion_14_.*\.png$/);
  expect(heat.tile).toBeGreaterThan(100000);
  expect(heat.heat).toBeGreaterThan(20);
  expect(heat.purple).toBe(0);
  await page.locator('.geo-session-toggle').click();
  await page.locator('.geo-session-option input').last().check();
  await page.getByRole('button', { name: 'Analizar sesiones', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Descargar mapa' })).toBeEnabled();
  await capture(page, testInfo, /^mapa_handovers_varias_sesiones_.*\.png$/);
});

test('exports the selected RSRQ layer and its legend', async ({ page }, testInfo) => {
  await prepare(page);
  await page.getByRole('tab', { name: 'Mapa de calor', exact: true }).click();
  await page.getByRole('radio', { name: 'RSRQ', exact: true }).check();
  await expect(page.locator('.geo-signal-heat-layer')).toBeVisible();
  await page.locator('.leaflet-control-zoom-out').click();
  await expect(page.locator('.geo-signal-legend')).toContainText('RSRQ ≤ -15 dB');
  const png = await capture(page, testInfo, /^mapa_calor_rsrq_sesion_14_.*\.png$/);
  expect(png.red).toBeGreaterThan(20);
  expect(png.tile).toBeGreaterThan(100000);
});

test('does not download an incomplete base map', async ({ page }) => {
  await prepare(page, { brokenTiles: true });
  let downloads = 0;
  page.on('download', () => downloads++);
  await page.getByRole('button', { name: 'Descargar mapa' }).click();
  await expect(page.getByRole('alert')).toContainText('El mapa base no terminó de cargar', { timeout: 18000 });
  expect(downloads).toBe(0);
  await expect(page.getByRole('button', { name: 'Descargar mapa' })).toBeEnabled();
});

test('disables export when the analysis has no measurements', async ({ page }) => {
  await prepare(page, { empty: true });
  await expect(page.getByRole('button', { name: 'Descargar mapa' })).toBeDisabled();
});
