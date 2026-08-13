const { test, expect } = require('@playwright/test');

test('dashboard renders without browser errors', async ({ page }) => {
  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));

  await page.goto('/');
  await expect(page).toHaveTitle(/Mail digest/);
  await expect(page.getByRole('heading', { name: /Less inbox/ })).toBeVisible();
  await expect(page.locator('.calendar')).toBeVisible();
  await expect(page.locator('.edition')).toHaveCount(1);
  await page.screenshot({ path: 'artifacts/calendar-desktop.png', fullPage: true });

  await page.locator('.edition').click();
  await expect(page.getByText('Top stories', { exact: true })).toBeVisible();
  await expect(page.getByText('Source newsletters', { exact: true })).toBeVisible();
  await expect(page.locator('details')).toHaveCount(3);
  expect(await page.locator('.story-link').count()).toBeGreaterThan(0);
  await expect(page.locator('.source-links a').first()).toHaveAttribute('href', /^https:\/\//);
  await expect(page.locator('.source-links a').first()).toHaveAttribute('target', '_blank');
  await page.screenshot({ path: 'artifacts/day-desktop.png', fullPage: true });
  expect(errors).toEqual([]);
});

test('calendar is readable on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.locator('.calendar')).toBeVisible();
  await page.screenshot({ path: 'artifacts/calendar-mobile.png', fullPage: true });
});
