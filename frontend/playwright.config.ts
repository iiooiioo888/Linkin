import { defineConfig, devices } from '@playwright/test';

/**
 * E2E：核心流程（建立對話 → 監控即時 → 角色／實驗室）。
 * 需先啟動 frontend（預設 localhost:3001，與 Vite 一致）與後端。
 * 覆寫：PLAYWRIGHT_BASE_URL
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3001',
    trace: 'on-first-retry',
    colorScheme: 'dark',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
