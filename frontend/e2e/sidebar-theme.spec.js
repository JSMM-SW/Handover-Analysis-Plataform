import { test, expect } from '@playwright/test';

test('theme switch stays visible on a long temporal page', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('handover-analysis-tema', 'claro'));
  await page.route('**/api/v1/**', (route) => route.fulfill({ json: [] }));
  await page.goto('/visualizacion-temporal');
  // Reproduce a page with several charts, independently of session availability.
  await page.locator('.app-content').evaluate((element) => { element.style.minHeight = '3000px'; });
  const toggle = page.getByRole('button', { name: 'Modo oscuro', exact: true });
  await expect(toggle).toBeInViewport();
  await page.evaluate(() => window.scrollTo(0, 1400));
  await expect(toggle).toBeInViewport();
  await toggle.click();
  await expect(page.locator('html')).toHaveAttribute('data-tema', 'oscuro');
  await expect(page.getByRole('button', { name: 'Modo claro', exact: true })).toBeInViewport();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(page.getByRole('button', { name: 'Modo claro', exact: true })).toBeInViewport();
});
