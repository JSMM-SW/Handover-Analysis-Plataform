import { test, expect } from '@playwright/test';

const points = [0, 1, 2].map((index) => ({
  id_registro: `point-${index}`, timestamp_medicion: `2026-05-05T13:00:0${index}Z`,
  latitud: -0.2 + index * 0.001, longitud: -78.5 + index * 0.001,
  cell_id: index === 2 ? 20 : 10, tecnologia: 1, rsrp_dbm: -85 - index * 15, hoja_origen: 'Datos 1',
}));

async function setup(page) {
  await page.route('**/api/v1/geoespacial/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/ejecuciones')) return route.fulfill({ json: [{ execution_id: 'test-execution', filename: 'Prueba.xlsx', processing_date: '2026-05-05T13:00:00Z', records_valid: 3 }] });
    if (url.pathname.endsWith('/hojas')) return route.fulfill({ json: ['Datos 1'] });
    const cell = url.searchParams.get('cell_id');
    const filtered = cell ? points.filter((p) => String(p.cell_id) === cell) : points;
    return route.fulfill({ json: { mediciones: filtered, total: filtered.length, tramos: filtered.length > 1 ? [filtered.map((p) => p.id_registro)] : [], advertencias: ['Mapa de calor de mediciones.'] } });
  });
}

test('navigation, map, layers, detail, filters and empty state', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await setup(page);
  await page.goto('/ingesta');
  await expect(page.getByRole('heading', { name: 'Carga de datos de handover' })).toBeVisible();
  await page.getByRole('link', { name: 'Geoespacial', exact: true }).click();
  await expect(page.getByText('Mediciones visibles').locator('..').locator('strong')).toHaveText('3');
  await expect(page.locator('.leaflet-control-zoom-in')).toBeVisible();
  const filterBox = await page.getByRole('complementary', { name: 'Filtros geoespaciales' }).boundingBox();
  const mapBox = await page.locator('.geo-map').boundingBox();
  expect(filterBox.x + filterBox.width).toBeLessThan(mapBox.x);
  await page.getByRole('tab', { name: 'Mapa de calor', exact: true }).click();
  await expect(page.locator('.leaflet-heatmap-layer')).toBeVisible();
  await page.getByRole('tab', { name: 'Mapa de rutas y handovers' }).click();
  await expect(page.locator('.leaflet-heatmap-layer')).toHaveCount(0);
  // Select the point located at the map's geographic midpoint.
  const map = page.locator('.geo-map');
  const box = await map.boundingBox();
  await map.click({ position: { x: box.width / 2, y: box.height / 2 } });
  await expect(page.getByRole('heading', { name: 'Detalle de medición' })).toBeVisible();
  await page.getByLabel('Celda', { exact: true }).fill('10');
  await page.getByRole('button', { name: 'Aplicar filtros' }).click();
  await expect(page.getByText('Mediciones visibles').locator('..').locator('strong')).toHaveText('2');
  await page.getByRole('tab', { name: 'Mapa de calor', exact: true }).click();
  await expect(page.getByLabel('Celda', { exact: true })).toHaveValue('10');
  await expect(page.getByText('Mediciones visibles').locator('..').locator('strong')).toHaveText('2');
  await page.getByRole('tab', { name: 'Mapa de calor', exact: true }).press('ArrowLeft');
  await expect(page.getByRole('tab', { name: 'Mapa de rutas y handovers' })).toHaveAttribute('aria-selected', 'true');
  await page.getByRole('button', { name: 'Filtrar por zona visible' }).click();
  await expect(page.getByText('Zona geográfica aplicada')).toBeVisible();
  await page.getByLabel('Celda', { exact: true }).fill('99');
  await page.getByRole('button', { name: 'Aplicar filtros' }).click();
  await expect(page.getByText('No hay mediciones que coincidan con estos filtros.')).toBeVisible();
  await page.getByRole('button', { name: 'Limpiar', exact: true }).click();
  await expect(page.getByText('Mediciones visibles').locator('..').locator('strong')).toHaveText('3');
  await page.screenshot({ path: 'test-results/geoespacial-desktop.png', fullPage: true });
  expect(errors).toEqual([]);
});

test('explicit Ecuador offset and layer preferences survive reload', async ({ page }) => {
  await setup(page);
  await page.goto('/geoespacial');
  await expect(page.getByText('Mediciones visibles').locator('..').locator('strong')).toHaveText('3');
  await page.getByLabel('Desde · Ecuador').fill('2026-05-05T08:00');
  const request = page.waitForRequest((r) => r.url().includes('/mediciones?') && r.url().includes('desde='));
  await page.getByRole('button', { name: 'Aplicar filtros' }).click();
  expect(new URL((await request).url()).searchParams.get('desde')).toBe('2026-05-05T08:00-05:00');
  await page.getByRole('checkbox', { name: 'Trayectoria aproximada' }).uncheck();
  await page.reload();
  await expect(page.getByRole('checkbox', { name: 'Trayectoria aproximada' })).not.toBeChecked();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('link', { name: 'Ingesta', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('shows API failure without presenting stale measurements', async ({ page }) => {
  await setup(page);
  await page.route('**/geoespacial/mediciones?**', (route) => route.fulfill({ status: 503, json: { detail: 'Base de datos no disponible.' } }));
  await page.goto('/geoespacial');
  await expect(page.getByRole('alert')).toHaveText('Base de datos no disponible.');
  await expect(page.getByText('Mediciones visibles').locator('..').locator('strong')).toHaveText('—');
});
