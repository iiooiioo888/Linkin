import { expect, test } from '@playwright/test';
import { passGate } from './gate';

const SURFACES = ['對話', '上下文壓縮', '提示詞壓縮', '歷史對話記錄'] as const;

test.describe('四入口殼', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await passGate(page);
  });

  test('畫面上只剩四個入口，對話可以輸入', async ({ page }) => {
    const nav = page.getByTestId('surface-nav');
    await expect(nav).toBeVisible();
    for (const label of SURFACES) {
      await expect(nav.getByRole('button', { name: label, exact: true })).toBeVisible();
    }
    await expect(nav.getByRole('button')).toHaveCount(4);
    await expect(page.getByPlaceholder(/輸入問題|輸入訊息/)).toBeVisible();
    await expect(nav.getByRole('button', { name: '對話' })).toHaveAttribute('aria-current', 'page');
  });

  test('三個入口都有畫面', async ({ page }) => {
    const nav = page.getByTestId('surface-nav');

    await nav.getByRole('button', { name: '上下文壓縮', exact: true }).click();
    await expect(page.getByTestId('context-compression')).toBeVisible();
    await expect(page.getByRole('button', { name: '帶入本機對話' })).toBeVisible();
    await expect(page.getByTestId('surface-unmounted')).toHaveCount(0);

    await nav.getByRole('button', { name: '提示詞壓縮', exact: true }).click();
    await expect(page.getByTestId('prompt-compression')).toBeVisible();
    await expect(page.getByRole('button', { name: '壓縮', exact: true })).toBeVisible();

    await nav.getByRole('button', { name: '歷史對話記錄', exact: true }).click();
    await expect(page.locator('[data-surface="history"]')).toBeVisible();
    await expect(page.getByRole('heading', { name: '歷史對話記錄' })).toBeVisible();
    await expect(page.getByTestId('surface-unmounted')).toHaveCount(0);
  });

  test('舊的公司與模組網址回到對話', async ({ page }) => {
    await page.goto('/#/company');
    await passGate(page);
    await expect(page).toHaveURL(/#\/chat$/);
    await expect(page.getByTestId('surface-nav').getByRole('button', { name: '對話' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await expect(page.getByPlaceholder(/輸入問題|輸入訊息/)).toBeVisible();

    await page.goto('/#/world/media-vault');
    await expect(page).toHaveURL(/#\/chat$/);
    await expect(page.getByTestId('media-vault-hub')).toHaveCount(0);
  });

  test('對話詳細區：/context 開啟底部 Context 面板', async ({ page }) => {
    await page.goto('/#/chat');
    await expect(page.getByTestId('chat-bottom-panel')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('chat-bottom-tab-context')).toBeVisible();
    await expect(page.getByTestId('chat-bottom-tab-context')).toContainText(/本對話/);

    const composer = page.getByPlaceholder(/輸入問題|輸入訊息/);
    await composer.fill('/context');
    await composer.press('Enter');

    await expect(page.getByTestId('chat-bottom-tab-context')).toHaveClass(/is-on/);
    await expect(page.getByTestId('chat-context-embed')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('context-panel-embed')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('chat-context-embed').getByText(/^Context$/)).toBeVisible();
    await expect(page.getByTestId('context-locked-task')).toBeVisible();
    await expect(page.getByTestId('context-locked-task')).toContainText(/本對話/);
    await expect(page.getByTestId('context-task-select')).toHaveCount(0);
    await expect(
      page.getByText(/本對話專屬|無任務選擇器|不可切換其他會話|僅顯示當前對話|本對話詳細區/),
    ).toBeVisible();
    await expect(page.url()).not.toMatch(/#\/monitor\/context/);
  });

  test('對話：/context peek 開啟浮動預覽模態（綁定本對話）', async ({ page }) => {
    await page.goto('/#/chat');
    const composer = page.getByPlaceholder(/輸入問題|輸入訊息/);
    await composer.fill('/context peek');
    await composer.press('Enter');

    await expect(page.getByRole('dialog', { name: 'Context' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('context-peek-locked')).toBeVisible();
    await expect(page.getByTestId('context-peek-locked')).toContainText(/本對話/);
    await expect(page.getByRole('button', { name: /對話詳細區/ })).toBeVisible();
    await expect(page.getByTestId('context-task-select')).toHaveCount(0);
    await expect(page.url()).not.toMatch(/#\/monitor\/context/);
  });
});
