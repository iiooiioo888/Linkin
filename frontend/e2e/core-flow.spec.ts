import { expect, test } from '@playwright/test';

test.describe('EvoLoop 核心 UI', () => {
  test('首頁載入並可切換控制台即時動態', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('body')).toBeVisible();

    await page.getByTitle('控制台').or(page.getByTitle('Console')).click();
    await expect(page.getByText('即時').or(page.getByText('Live')).first()).toBeVisible();

    await page.getByRole('button', { name: /即時|Live/ }).first().click();
    await expect(page.getByText(/LIVE|IDLE|待命|即時/).first()).toBeVisible({ timeout: 15_000 });
  });

  test('實驗室面板可開啟提示詞優化', async ({ page }) => {
    await page.goto('/#/monitor/lab');
    await expect(page.getByText(/實驗室 · 提示詞|Lab · Prompt/)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/優化前|Before/)).toBeVisible({ timeout: 15_000 });

    await page.reload();
    await expect(page.url()).toMatch(/#\/monitor\/lab/);
  });

  test('即時看板整合工具可跳轉至實驗室 firecrawl', async ({ page }) => {
    await page.goto('/#/monitor');
    await page.getByRole('button', { name: '爬蟲' }).first().click();
    await expect(page.getByText(/實驗室 · 爬蟲|Lab ·/)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/單頁抓取|Scrape/)).toBeVisible({ timeout: 10_000 });
    await expect(page.url()).toMatch(/#\/monitor\/lab\/firecrawl/);
  });

  test('Hash 路由：#/monitor/lab/firecrawl 可書籤與刷新還原', async ({ page }) => {
    await page.goto('/#/monitor/lab/firecrawl');
    await expect(page.getByText(/實驗室 · 爬蟲|Lab ·/)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/單頁抓取|Scrape/)).toBeVisible({ timeout: 10_000 });

    await page.reload();
    await expect(page.url()).toMatch(/#\/monitor\/lab\/firecrawl/);
  });

  test('角色分頁可開啟名冊', async ({ page }) => {
    await page.goto('/');
    await page.getByTitle('控制台').or(page.getByTitle('Console')).click();
    await page.getByRole('button', { name: /角色|Agents/ }).click();
    await expect(page.getByPlaceholder(/搜尋角色|Search roles/)).toBeVisible({ timeout: 15_000 });
  });

  test('Hash 路由：#/monitor/tasks 可書籤與刷新還原', async ({ page }) => {
    await page.goto('/#/monitor/tasks');
    await expect(page.getByText(/控制台 · 任務|Console ·/)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByPlaceholder(/搜尋任務|Search tasks/i)).toBeVisible({ timeout: 10_000 });

    await page.reload();
    await expect(page.getByText(/控制台 · 任務|Console ·/)).toBeVisible({ timeout: 10_000 });
    await expect(page.url()).toMatch(/#\/monitor\/tasks/);
  });

  test('Hash 路由：#/traces 可書籤與刷新還原', async ({ page }) => {
    await page.goto('/#/traces');
    await expect(page.getByText(/控制台 · 軌跡|執行軌跡|Traces/i).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByPlaceholder(/搜尋任務 ID|Search task ID/i)).toBeVisible({ timeout: 10_000 });

    await page.reload();
    await expect(page.url()).toMatch(/#\/traces/);
  });

  test('管線分頁「任務監控」跳轉至 tasks 分頁', async ({ page }) => {
    await page.goto('/#/monitor/pipeline');
    await page.getByRole('button', { name: /任務監控/ }).click();
    await expect(page.getByText(/控制台 · 任務|Console ·/)).toBeVisible({ timeout: 10_000 });
    await expect(page.url()).toMatch(/#\/monitor\/tasks/);
  });

    test('Hash 路由：#/monitor/world 可開啟靈境世界觀', async ({ page }) => {
    await page.goto('/#/monitor/world');
    await expect(page.getByText(/世界觀憲法|Constitution/).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.url()).toMatch(/#\/monitor\/world/);

    await page.reload();
    await expect(page.url()).toMatch(/#\/monitor\/world/);
  });
});
