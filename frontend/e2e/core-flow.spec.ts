import { expect, test } from '@playwright/test';
import { passGate } from './gate';

test.describe('EvoLoop 核心 UI', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await passGate(page);
  });
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

  test('Hash 路由：#/monitor/lab/maps 顯示策略可視化', async ({ page }) => {
    await page.goto('/#/monitor/lab/maps');
    await expect(page.getByText(/實驗室 · 策略圖|Lab ·/)).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.sq-tree-title', { hasText: '策略圖' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('【移動平均線】')).toBeVisible();
    await expect(page.getByText('角色引用')).toBeVisible();
    await expect(page.getByText('Archify', { exact: false }).first()).toBeVisible();
    await expect(page.locator('iframe.archify-frame, [role="img"]').first()).toBeVisible({ timeout: 30_000 });

    await page.reload();
    await expect(page.url()).toMatch(/#\/monitor\/lab\/maps/);
  });

  test('Hash 路由：#/monitor/lab/quant 顯示回測策略庫', async ({ page }) => {
    await page.goto('/#/monitor/lab/quant');
    await expect(page.getByText(/實驗室 · 策略庫|Lab ·/)).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.sq-tree-title', { hasText: '策略庫' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('【移動平均線】')).toBeVisible();
    await expect(page.getByText('角色引用')).toBeVisible();
    await expect(page.getByText('權益曲線')).toBeVisible();
    await expect(page.locator('iframe.archify-frame, [role="img"]').first()).toBeVisible({ timeout: 30_000 });

    await page.reload();
    await expect(page.url()).toMatch(/#\/monitor\/lab\/quant/);
  });

  test('量化角色工作台可開啟回測策略庫', async ({ page }) => {
    await page.goto('/#/monitor/agents');
    await expect(page.getByPlaceholder(/搜尋角色|Search roles/)).toBeVisible({ timeout: 15_000 });
    await page.getByPlaceholder(/搜尋角色|Search roles/).fill('量化');
    await page.locator('.ar-ri', { hasText: '量化分析師' }).click();
    await page.locator('.rd-header .rd-acts').getByRole('button', { name: '策略庫' }).click();
    await expect(page.getByRole('heading', { name: '回測策略庫' })).toBeVisible();
    await expect(page.locator('.sq-tree-title', { hasText: '策略庫' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('【移動平均線】')).toBeVisible();
    await expect(page.getByText('角色引用')).toBeVisible();
  });

  test('角色分頁可開啟名冊', async ({ page }) => {
    await page.goto('/');
    await page.getByTitle('控制台').or(page.getByTitle('Console')).click();
    await page.getByRole('navigation', { name: '控制台' }).getByRole('button', { name: /角色|Agents/ }).click();
    await expect(page.getByPlaceholder(/搜尋角色|Search roles/)).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('.ar-ri', { hasText: '建築總監' })).toHaveCount(0);
    await expect(page.locator('.ar-ri', { hasText: '建築執行者' })).toHaveCount(0);
    await expect(page.locator('.rd-header .rd-acts').getByRole('button', { name: '新增' })).toHaveCount(0);
    await expect(page.getByText('組織回報鏈')).toBeVisible();
    await expect(page.getByRole('heading', { name: /質詢鏈與任用/ })).toBeVisible();
    await expect(page.locator('.raho-org-h', { hasText: '指揮鏈' })).toBeVisible();
    await expect(page.locator('.rd-tree .rd-tree-lvl').first()).toHaveText(/L\d/);
    await expect(page.locator('.rd-onode.cur')).toBeVisible();
    await expect(page.locator('.rd-col-h', { hasText: '隊列' })).toBeVisible();
    await expect(page.locator('.rd-col-h', { hasText: '執行中' })).toBeVisible();
    await expect(page.locator('.rd-col-h', { hasText: '已完成' })).toBeVisible();
  });

  test('舊質詢樹路徑會開融合後的角色工作台', async ({ page }) => {
    await page.goto('/#/monitor/grill');
    await expect(page.getByPlaceholder(/搜尋角色|Search roles/)).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('.rd-header .rd-acts').getByRole('button', { name: '質詢' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /工作台/ })).toBeVisible();
    await expect(page.getByText(/角色即質詢節點|指揮鏈|點層級/)).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.locator('.rd-col-h', { hasText: '隊列' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: '控制台' }).getByRole('button', { name: /質詢樹/ })).toHaveCount(0);
  });

  test('Hash 路由：#/monitor/tasks 可書籤與刷新還原', async ({ page }) => {
    await page.goto('/#/monitor/tasks');
    await expect(page.getByRole('button', { name: '新項' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByPlaceholder(/搜尋任務|Search tasks/i)).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.rd-col-h', { hasText: '隊列' })).toBeVisible();
    await expect(page.locator('.rd-col-h', { hasText: '執行中' })).toBeVisible();
    await expect(page.locator('.rd-col-h', { hasText: '已完成' })).toBeVisible();

    await page.reload();
    await expect(page.getByPlaceholder(/搜尋任務|Search tasks/i)).toBeVisible({ timeout: 10_000 });
    await expect(page.url()).toMatch(/#\/monitor\/tasks/);
  });

  test('Hash 路由：#/traces 可書籤與刷新還原', async ({ page }) => {
    await page.goto('/#/traces');
    await expect(page.getByText(/執行軌跡|軌跡|Traces/i).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByPlaceholder(/搜尋任務 ID|Search task ID/i)).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.rd-col-h', { hasText: '隊列' })).toBeVisible();
    await expect(page.locator('.rd-col-h', { hasText: '執行中' })).toBeVisible();
    await expect(page.locator('.rd-col-h', { hasText: '已完成' })).toBeVisible();

    await page.reload();
    await expect(page.url()).toMatch(/#\/traces/);
  });

  test('管線分頁「任務監控」跳轉至 tasks 分頁', async ({ page }) => {
    await page.goto('/#/monitor/pipeline');
    await expect(page.locator('.rd-col-h', { hasText: '隊列' })).toBeVisible();
    await expect(page.locator('.rd-col-h', { hasText: '執行中' })).toBeVisible();
    await expect(page.locator('.rd-col-h', { hasText: '已完成' })).toBeVisible();
    await page.getByRole('button', { name: /任務監控/ }).click();
    await expect(page.getByPlaceholder(/搜尋任務|Search tasks/i)).toBeVisible({ timeout: 10_000 });
    await expect(page.url()).toMatch(/#\/monitor\/tasks/);
  });

  test('Hash 路由：#/monitor/world 可開啟靈境世界觀', async ({ page }) => {
    await page.goto('/#/monitor/world');
    await expect(page.getByText(/靈境 · .*世界觀|Linkin ·/).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/世界觀憲法|Constitution/).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.url()).toMatch(/#\/monitor\/world/);

    await page.reload();
    await expect(page.url()).toMatch(/#\/monitor\/world/);
  });

  test('Hash 路由：#/monitor/llm 可開啟 API 路由', async ({ page }) => {
    await page.goto('/#/monitor/llm');
    await expect(page.getByRole('button', { name: '權限' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/全域分發策略|已配置的 API/).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.url()).toMatch(/#\/monitor\/llm/);

    await page.reload();
    await expect(page.url()).toMatch(/#\/monitor\/llm/);
  });

  test('即時看板工作流可跳轉 API 路由', async ({ page }) => {
    await page.goto('/#/monitor');
    await page.getByRole('button', { name: '配置 API' }).click();
    await expect(page.getByText(/全域分發策略|已配置的 API/).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.url()).toMatch(/#\/monitor\/llm/);
  });

  test('Hash 路由：#/monitor/minecraft 可開啟 MCP 橋接', async ({ page }) => {
    await page.goto('/#/monitor/minecraft');
    await expect(page.getByText(/Minecraft · .*橋接/).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Minecraft MCP/).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.url()).toMatch(/#\/monitor\/minecraft/);

    await page.reload();
    await expect(page.url()).toMatch(/#\/monitor\/minecraft/);
  });

  test('活動欄：控制台與靈境不含 Minecraft，獨立活動可進橋接', async ({ page }) => {
    await page.goto('/');
    await page.getByTitle('控制台').or(page.getByTitle('Console')).click();
    await expect(page.getByRole('button', { name: /即時|Live/ }).first()).toBeVisible();
    await expect(page.getByRole('navigation', { name: '控制台' }).getByRole('button', { name: /世界觀/ })).toHaveCount(0);
    await expect(page.getByRole('navigation', { name: '控制台' }).getByRole('button', { name: /橋接/ })).toHaveCount(0);

    await page.getByTitle('靈境').or(page.getByTitle('Linkin')).click();
    await expect(page.getByRole('button', { name: /世界觀/ }).first()).toBeVisible();
    await expect(page.getByRole('navigation', { name: '靈境' }).getByRole('button', { name: /橋接/ })).toHaveCount(0);
    await expect(page.getByRole('navigation', { name: '靈境' }).getByRole('button', { name: /建築/ })).toHaveCount(0);
    await expect(page.getByRole('navigation', { name: '靈境' }).getByRole('button', { name: /工作室角色/ })).toBeVisible();

    await page.getByTitle('Minecraft').click();
    await expect(page.getByRole('button', { name: /建築/ }).first()).toBeVisible();
    await page.getByRole('button', { name: /橋接/ }).click();
    await expect(page.getByText(/Minecraft MCP/).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.url()).toMatch(/#\/monitor\/minecraft/);
  });

  test('靈境工作室角色不進控制台執行-角色', async ({ page }) => {
    await page.goto('/#/monitor/agents');
    await expect(page.getByPlaceholder(/搜尋角色|Search roles/)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('button', { name: '執行-角色' })).toBeVisible();
    await expect(page.locator('.ar-ri', { hasText: '建築總監' })).toHaveCount(0);
    await expect(page.locator('.rd-header .rd-acts').getByRole('button', { name: /^新增$/ })).toHaveCount(0);

    await page.goto('/#/monitor/studio');
    await expect(page.getByText(/靈境 · .*工作室/).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByPlaceholder(/搜尋角色|Search roles/)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('建築總監').first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('建築執行者').first()).toBeVisible();
    await expect(page.url()).toMatch(/#\/monitor\/studio/);
  });
});
