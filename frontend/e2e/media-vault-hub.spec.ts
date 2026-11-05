import { expect, test } from '@playwright/test';
import { passGate } from './gate';

test.describe('Media Vault Hub', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await passGate(page);
  });

  test('实验室 → 媒体库 Hub → 切换页签', async ({ page }) => {
    await page.goto('/#/monitor/lab');
    const labNav = page.getByRole('navigation', { name: '實驗室' });
    await labNav.getByRole('link', { name: /采集 · 媒体库/ }).click();

    await expect(page.getByTestId('media-vault-hub')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('media-vault-tab-control')).toBeVisible();
    await expect(page.getByTestId('media-vault-control')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('mediacrawler-panel')).toBeVisible();

    await page.getByTestId('media-vault-tab-monitor').click();
    await expect(page.getByTestId('media-vault-monitor')).toBeVisible({ timeout: 10_000 });

    await page.getByTestId('media-vault-tab-gallery').click();
    await expect(page.getByTestId('media-vault-gallery')).toBeVisible({ timeout: 10_000 });

    await expect(page.getByTestId('media-vault-related-repos')).toBeVisible();
    await expect(page.getByRole('link', { name: /Linkin（本 runtime）/ })).toHaveAttribute(
      'href',
      'https://github.com/iiooiioo888/Linkin',
    );
    await expect(page.getByRole('link', { name: /LinkinL/ })).toHaveAttribute(
      'href',
      'https://github.com/iiooiioo888/LinkinL',
    );
    await expect(page.getByRole('link', { name: /线上站点/ })).toHaveAttribute(
      'href',
      'https://iiooiioo888.github.io/LinkinL/',
    );
  });
});
