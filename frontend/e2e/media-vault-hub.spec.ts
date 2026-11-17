import { expect, test } from '@playwright/test';
import { passGate } from './gate';

test.describe('媒體庫不再是入口', () => {
  test('主導覽沒有媒體庫，舊網址回到對話', async ({ page }) => {
    await page.goto('/');
    await passGate(page);
    const nav = page.getByTestId('surface-nav');
    await expect(nav.getByRole('button')).toHaveCount(4);
    await expect(nav.getByText('媒體庫')).toHaveCount(0);
    await expect(page.getByTestId('media-vault-hub')).toHaveCount(0);

    await page.goto('/#/modules/media-vault');
    await expect(page).toHaveURL(/#\/chat$/);
    await expect(page.getByTestId('media-vault-hub')).toHaveCount(0);
  });
});