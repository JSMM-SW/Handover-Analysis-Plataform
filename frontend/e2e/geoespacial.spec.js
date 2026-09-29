import { test, expect } from '@playwright/test';

test('CSV sessions load without sheet or RSSI', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.route('**/api/v1/geoespacial/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/ejecuciones')) return route.fulfill({ json: [{ execution_id: 'csv-session', sesion_label: 14, filename: 'mediciones.csv', processing_date: '2026-05-05T13:00:00Z', fecha_inicio: '2026-05-05T13:00:00Z', fecha_fin: '2026-05-05T13:40:58Z' }] });
    if (url.pathname.endsWith('/hojas')) return route.fulfill({ json: [null] });
    expect(url.searchParams.has('hoja')).toBe(false);
    const point = { ...points[0], timestamp_medicion: '2026-05-05T13:40:58Z', hoja_origen: null, rsrp_dbm: null, rssi: null, tecnologia: 2 };
    return route.fulfill({ json: { mediciones: [point], total: 1, handovers: [{ ...point, celda_origen: 5, nodo_origen: 100, node_id: 200 }], total_handovers: 1, tramos: [], advertencias: [] } });
  });
  await page.goto('/geoespacial');
  await page.getByRole('button', { name: /Selecciona las sesiones para analizar/ }).click();
  await expect(page.getByRole('checkbox', { name: /Sesión 14/ })).toBeVisible();
  await expect(page.getByText('mediciones.csv')).toHaveCount(0);
  await page.locator('.geo-session-option input').first().check();
  await page.getByRole('button', { name: 'Analizar sesiones', exact: true }).click();
  await expect(page.getByText('Datos analizados').locator('..').locator('strong')).toHaveText('1');
  await expect(page.getByText('RSSI promedio').locator('..').locator('strong')).toHaveText('—');
  const map = page.locator('.geo-map');
  const box = await map.boundingBox();
  await map.hover({ position: { x: box.width / 2, y: box.height / 2 } });
  await expect(page.locator('.leaflet-tooltip .geo-handover-tooltip')).toContainText('Hora: 08:40:58');
  await page.getByRole('combobox', { name: 'Tecnología', exact: true }).selectOption('2');
  await page.getByRole('button', { name: 'Aplicar filtros' }).click();
  await expect(page.getByText('Datos analizados').locator('..').locator('strong')).toHaveText('1');
  expect(errors).toEqual([]);
});

const points = [0, 1, 2].map((index) => ({
  id_registro: `point-${index}`, timestamp_medicion: `2026-05-05T13:00:0${index}Z`,
  latitud: -0.2 + index * 0.001, longitud: -78.5 + index * 0.001,
  cell_id: index === 2 ? 20 : 10, tecnologia: 1, rsrp_dbm: -85 - index * 15, rssi: -75, rsrq: -8 - index * 4, rssnr: 12, hoja_origen: 'Datos 1',
}));

async function setup(page) {
  await page.route('**/api/v1/geoespacial/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/ejecuciones')) return route.fulfill({ json: [{ execution_id: 'test-execution', sesion_label: 15, filename: 'Prueba.xlsx', processing_date: '2026-05-05T13:00:00Z', records_valid: 3, fecha_inicio: '2026-05-05T13:00:00Z', fecha_fin: '2026-05-05T13:00:02Z' }] });
    if (url.pathname.endsWith('/hojas')) return route.fulfill({ json: ['Datos 1'] });
    const cell = url.searchParams.get('cell_id');
    const filtered = url.searchParams.get('tecnologia') === '0' ? [] : cell ? points.filter((p) => String(p.cell_id) === cell) : points;
    return route.fulfill({ json: { mediciones: filtered, total: filtered.length, handovers: filtered.length ? [{ ...points[1], celda_origen: 5, nodo_origen: 100, node_id: 200 }] : [], total_handovers: filtered.length ? 1 : 0, tramos: filtered.length > 1 ? [filtered.map((p) => p.id_registro)] : [], advertencias: ['Mapa de calor de mediciones.'] } });
  });
}

test('navigation, map, layers, detail, filters and empty state', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await setup(page);
  await page.goto('/ingesta');
  await expect(page.getByRole('heading', { name: 'Carga de datos de handover' })).toBeVisible();
  await page.getByRole('link', { name: 'Geoespacial', exact: true }).click();
  await page.getByRole('button', { name: /Selecciona las sesiones para analizar/ }).click();
  await page.locator('.geo-session-option input').first().check();
  await page.getByRole('button', { name: 'Analizar sesiones', exact: true }).click();
  await expect(page.getByText('Datos analizados').locator('..').locator('strong')).toHaveText('3');
  await expect(page.getByText('RSSI promedio').locator('..').locator('strong')).toHaveText('-75 dBm');
  await expect(page.locator('.leaflet-control-zoom-in')).toBeVisible();
  const filterBox = await page.getByRole('complementary', { name: 'Filtros geoespaciales' }).boundingBox();
  const mapBox = await page.locator('.geo-map').boundingBox();
  expect(filterBox.x + filterBox.width).toBeLessThan(mapBox.x);
  await page.getByRole('tab', { name: 'Mapa de calor', exact: true }).click();
  await expect(page.locator('.leaflet-heatmap-layer')).toBeVisible();
  await expect(page.getByRole('radio', { name: 'Handovers', exact: true })).toBeChecked();
  await expect(page.getByRole('checkbox', { name: 'Mapa de calor', exact: true })).toHaveCount(0);
  await expect(page.getByRole('checkbox', { name: 'Trayectoria', exact: true })).toHaveCount(0);
  await page.getByRole('radio', { name: 'RSSI', exact: true }).check();
  await expect(page.locator('.geo-signal-heat-layer')).toBeVisible();
  await expect(page.locator('.leaflet-heatmap-layer')).toHaveCount(0);
  await expect(page.locator('.geo-signal-legend')).toContainText('RSSI en handovers');
  await page.getByRole('radio', { name: 'RSRQ', exact: true }).check();
  await expect(page.locator('.geo-signal-legend')).toContainText('RSRQ en handovers');
  await page.getByRole('radio', { name: 'Handovers', exact: true }).check();
  await expect(page.locator('.geo-signal-heat-layer')).toHaveCount(0);
  await expect(page.locator('.leaflet-heatmap-layer')).toBeVisible();
  await page.getByRole('tab', { name: 'Mapa de rutas y handovers' }).click();
  await expect(page.locator('.leaflet-heatmap-layer')).toHaveCount(0);
  // Select the point located at the map's geographic midpoint.
  const map = page.locator('.geo-map');
  const box = await map.boundingBox();
  await map.hover({ position: { x: box.width / 2, y: box.height / 2 } });
  const bubble = page.locator('.leaflet-tooltip .geo-handover-tooltip');
  await expect(bubble).toBeVisible();
  await expect(bubble).toContainText('Fecha:');
  await expect(bubble).toContainText('Hora: 08:00:01');
  await expect(bubble).toContainText('RSSI: -75 dBm');
  await expect(bubble).toContainText('RSRQ: -12 dB');
  await expect(bubble).toContainText('RSSNR: 12');
  await map.click({ position: { x: box.width / 2, y: box.height / 2 } });
  await expect(page.getByRole('heading', { name: 'Detalle de handover' })).toBeVisible();
  await expect(page.getByText('RSSI', { exact: true }).locator('..').locator('dd')).toHaveText('-75 dBm');
  await expect(page.locator('input[name="cell_id"]')).toHaveCount(0);
  await expect(page.getByLabel('Hoja de medici\u00f3n')).toHaveCount(0);
  await expect(page.locator('.geo-stats').getByText('Handovers', { exact: true })).toBeVisible();
  await page.getByRole('tab', { name: 'Mapa de calor', exact: true }).click();
  await expect(page.getByText('Datos analizados').locator('..').locator('strong')).toHaveText('3');
  await page.getByRole('tab', { name: 'Mapa de calor', exact: true }).press('ArrowLeft');
  await expect(page.getByRole('tab', { name: 'Mapa de rutas y handovers' })).toHaveAttribute('aria-selected', 'true');
  await page.getByRole('button', { name: 'Filtrar por zona visible' }).click();
  await page.getByRole('combobox', { name: 'Tecnolog\u00eda', exact: true }).selectOption('0');
  await page.getByRole('button', { name: 'Aplicar filtros' }).click();
  await expect(page.getByText('No hay mediciones que coincidan con estos filtros.')).toBeVisible();
  await page.getByRole('button', { name: 'Limpiar', exact: true }).click();
  await expect(page.getByText('Datos analizados').locator('..').locator('strong')).toHaveText('3');
  await page.screenshot({ path: 'test-results/geoespacial-desktop.png', fullPage: true });
  expect(errors).toEqual([]);
});

test('explicit Ecuador offset and layer preferences survive reload', async ({ page }) => {
  await setup(page);
  await page.goto('/geoespacial');
  await page.getByRole('button', { name: /Selecciona las sesiones para analizar/ }).click();
  await page.locator('.geo-session-option input').first().check();
  await page.getByRole('button', { name: 'Analizar sesiones', exact: true }).click();
  await expect(page.getByText('Datos analizados').locator('..').locator('strong')).toHaveText('3');
  await expect(page.locator('input[name=desde]')).toHaveAttribute('step', '60');
  await expect(page.locator('input[name=hasta]')).toHaveAttribute('step', '60');
  await page.getByLabel('Hasta').fill('2026-05-05T08:01');
  await page.getByLabel('Desde').fill('2026-05-05T08:00');
  const request = page.waitForRequest((r) => r.url().includes('/mediciones?') && r.url().includes('desde='));
  await page.getByRole('button', { name: 'Aplicar filtros' }).click();
  const params = new URL((await request).url()).searchParams;
  expect(params.get('desde')).toBe('2026-05-05T08:00:00-05:00');
  expect(params.get('hasta')).toBe('2026-05-05T08:01:59.999999-05:00');
  await page.getByRole('checkbox', { name: 'Trayectoria' }).uncheck();
  await page.reload();
  await page.getByRole('button', { name: /Selecciona las sesiones para analizar/ }).click();
  await page.locator('.geo-session-option input').first().check();
  await page.getByRole('button', { name: 'Analizar sesiones', exact: true }).click();
  await expect(page.getByRole('checkbox', { name: 'Trayectoria' })).not.toBeChecked();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('link', { name: 'Ingesta', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('selects several sessions and shows their combined date range', async ({ page }) => {
  const requested = [];
  await page.route('**/api/v1/geoespacial/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/ejecuciones')) return route.fulfill({ json: [
      { execution_id: 'first', sesion_label: 21, filename: 'uno.csv', records_valid: 2, fecha_inicio: '2026-05-05T13:00:00Z', fecha_fin: '2026-05-05T14:00:00Z' },
      { execution_id: 'second', sesion_label: 22, filename: 'dos.csv', records_valid: 2, fecha_inicio: '2026-05-06T15:00:00Z', fecha_fin: '2026-05-06T16:00:00Z' },
    ] });
    requested.push(url.searchParams.getAll('execution_id'));
    const selected = url.searchParams.getAll('execution_id');
    const mediciones = selected.map((id, index) => ({ ...points[index], id_registro: id, execution_id: id }));
    return route.fulfill({ json: { mediciones, total: mediciones.length, handovers: [], total_handovers: 0, tramos: [], advertencias: [] } });
  });
  await page.goto('/geoespacial');
  await page.getByRole('button', { name: /Selecciona las sesiones para analizar/ }).click();
  await expect(page.getByText('Selecciona una o varias sesiones para ver los mapas.')).toBeVisible();
  await page.getByRole('checkbox', { name: /Sesión 21/ }).check();
  await expect(page.locator('.geo-date-range')).toContainText('5/5/26');
  await page.getByRole('checkbox', { name: /Sesión 22/ }).check();
  expect(requested).toEqual([]);
  await expect(page.locator('.geo-map')).toHaveCount(0);
  await page.getByRole('button', { name: 'Analizar sesiones', exact: true }).click();
  await expect(page.locator('.geo-date-range')).toContainText('6/5/26');
  await expect(page.getByText('Datos analizados').locator('..').locator('strong')).toHaveText('2');
  expect(requested.some((ids) => ids.length === 2 && ids.includes('first') && ids.includes('second'))).toBe(true);
  await expect(page.locator('.geo-session-toggle')).toHaveAttribute('aria-expanded', 'false');
  await expect(page.locator('.geo-session-toggle')).toContainText('Sesión 21, Sesión 22');
  await page.locator('.geo-session-toggle').click();
  await page.getByRole('checkbox', { name: /Sesión 21/ }).uncheck();
  await expect(page.getByText('Datos analizados').locator('..').locator('strong')).toHaveText('2');
  await page.getByRole('button', { name: 'Analizar sesiones', exact: true }).click();
  await expect(page.getByText('Datos analizados').locator('..').locator('strong')).toHaveText('1');
});

test('shows API failure without presenting stale measurements', async ({ page }) => {
  await setup(page);
  await page.route('**/geoespacial/mediciones?**', (route) => route.fulfill({ status: 503, json: { detail: 'Base de datos no disponible.' } }));
  await page.goto('/geoespacial');
  await page.getByRole('button', { name: /Selecciona las sesiones para analizar/ }).click();
  await page.locator('.geo-session-option input').first().check();
  await page.getByRole('button', { name: 'Analizar sesiones', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('Base de datos no disponible.');
  await expect(page.getByText('Datos analizados').locator('..').locator('strong')).toHaveText('—');
});

test('radio base layer shows estimated positions, coincident sessions and insufficient data', async ({ page }) => {
  await setup(page);
  await page.route('**/geoespacial/ejecuciones*', (route) => route.fulfill({ json: [
    { execution_id: 'first', sesion_label: 21, records_valid: 3 },
    { execution_id: 'second', sesion_label: 22, records_valid: 3 },
  ] }));
  await page.route('**/geoespacial/mediciones?**', (route) => {
    const filtered = new URL(route.request().url()).searchParams.get('tecnologia') === '2';
    const station = { id: 'candidate', execution_id: 'first', latitud: points[1].latitud, longitud: points[1].longitud,
      node_id: 100, cell_id: 10, tecnologia: 1, earfcn: 1700, psc_pci: [0, 21],
      mediciones_validas: 20, posiciones_disponibles: 10, posiciones_utilizadas: 5, rssi_max: -70, dispersion_m: 45 };
    return route.fulfill({ json: { mediciones: points, total: 3, handovers: [], total_handovers: 0, tramos: [], advertencias: [],
      radios_base: filtered ? [] : [station, { ...station, id: 'second-candidate', execution_id: 'second' }],
      resumen_radios_base: { grupos_evaluados: 2, grupos_insuficientes: filtered ? 2 : 0, mediciones_descartadas: 1, duplicados_descartados: 3, motivos: { 'RSSI ausente': 1 } },
    } });
  });
  await page.goto('/geoespacial');
  await page.getByRole('button', { name: /Selecciona las sesiones para analizar/ }).click();
  await page.locator('.geo-session-option input').first().check();
  await page.getByRole('button', { name: 'Analizar sesiones', exact: true }).click();
  await expect(page.getByText('Datos analizados').locator('..').locator('strong')).toHaveText('3');
  await expect(page.locator('.geo-radio-base-marker')).toHaveCount(0);
  await page.getByRole('checkbox', { name: 'Radios Base', exact: true }).check();
  await expect(page.getByText('Número de estimaciones: 2', { exact: true })).toBeVisible();
  await expect(page.locator('.geo-radio-base-marker')).toHaveCount(1);
  await page.locator('.geo-radio-base-marker').click();
  const popup = page.locator('.geo-radio-popup');
  await expect(popup).toContainText('Sesión: 21');
  await expect(popup).toContainText('Sesión: 22');
  await expect(popup.getByText('Ubicación aproximada calculada a partir de las mediciones.').first()).toBeVisible();
  await expect(popup.getByText('PCI: 0, 21', { exact: true }).first()).toBeHidden();
  await popup.locator('summary').first().click();
  await expect(popup.getByText('PCI: 0, 21', { exact: true }).first()).toBeVisible();
  await expect(popup).toContainText('no es el error de ubicación');
  await page.getByRole('tab', { name: 'Mapa de calor', exact: true }).click();
  await expect(page.locator('.geo-radio-base-marker')).toHaveCount(0);
  await expect(page.locator('.geo-radio-popup')).toHaveCount(0);
  await page.getByRole('tab', { name: 'Mapa de rutas y handovers', exact: true }).click();
  await expect(page.locator('.geo-radio-base-marker')).toHaveCount(1);
  await page.getByRole('checkbox', { name: 'Radios Base', exact: true }).uncheck();
  await expect(page.locator('.geo-radio-base-marker')).toHaveCount(0);
  await page.getByRole('checkbox', { name: 'Radios Base', exact: true }).check();
  await page.getByRole('combobox', { name: 'Tecnología', exact: true }).selectOption('2');
  await page.getByRole('button', { name: 'Aplicar filtros' }).click();
  await expect(page.getByText('Número de estimaciones: 0', { exact: true })).toBeVisible();
  await expect(page.locator('.geo-radio-base-marker')).toHaveCount(0);
});
