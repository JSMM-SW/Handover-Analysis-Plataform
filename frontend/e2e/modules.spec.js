import { test, expect } from '@playwright/test';

test('shared navigation opens all modules and preserves temporal legacy links', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/v1/visualizacion-temporal/sesiones', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/geoespacial/ejecuciones*', (route) => route.fulfill({ json: [] }));

  await page.goto('/#/visualizacion-temporal');
  await expect(page).toHaveURL(/\/visualizacion-temporal$/);
  await expect(page.getByRole('heading', { name: 'Visualización temporal de handovers', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Visualización geoespacial', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Explora tus mediciones' })).toBeVisible();
  await page.getByRole('link', { name: 'Procesamiento de datos', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Carga de datos de handover' })).toBeVisible();
  await page.getByRole('link', { name: 'Visualización temporal', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Visualización temporal de handovers', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Visualización temporal de handovers', exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('link', { name: 'Visualización geoespacial', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
