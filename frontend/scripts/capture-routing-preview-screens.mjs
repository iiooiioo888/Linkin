/**
 * 截圖：路由預覽（真實 POST /routing/preview，需本機後端 + Vite dev）。
 * 後端建議：LINKIN_AUTH_DISABLED=1 python3 -m backend.main
 * 前端：npm run dev -- --port 3001
 */
import { chromium, devices } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

const OUT = '/opt/cursor/artifacts/screenshots';
const BASE = process.env.PREVIEW_BASE ?? 'http://127.0.0.1:3001';

async function loginViaApi(page) {
  const token = await page.evaluate(async () => {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'alice', password: 's3cret-test' }),
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    const rec = { t: data.token, u: data.user, exp: Date.now() + 86400000 };
    localStorage.setItem('evoloop.runtime', JSON.stringify(rec));
    localStorage.setItem('linkin.onboarding.dismissed', '1');
    localStorage.setItem('linkin.chat.emptyHint.dismissed', '1');
    window.dispatchEvent(new Event('linkin-auth-changed'));
    return data.token;
  });
  if (!token) throw new Error('auth/login failed — 請確認後端 LINKIN_GATE_ID=alice');
}

async function captureComposer(page, name) {
  const bar = page.locator('.apple-input-bar');
  await bar.waitFor({ state: 'visible', timeout: 20000 });
  await page.waitForSelector('[data-testid="routing-preview-chips"]', { timeout: 15000 });
  await page.waitForTimeout(400);
  await bar.screenshot({ path: path.join(OUT, name) });
}

async function main() {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch();

  {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await page.goto(`${BASE}/`);
    await loginViaApi(page);
    await page.reload({ waitUntil: 'load' });
    await page.goto(`${BASE}/#/chat`, { waitUntil: 'load' });
    const field = page.locator('textarea').first();
    await field.waitFor({ state: 'visible', timeout: 20000 });
    await field.fill('在灵境精灵森林建造一座树桥聚落');
    await page.waitForTimeout(500);
    await captureComposer(page, 'routing-preview-desktop-1440.png');
    await context.close();
  }

  {
    const context = await browser.newContext({
      ...devices['iPhone 12'],
      viewport: { width: 390, height: 844 },
    });
    const page = await context.newPage();
    await page.goto(`${BASE}/`);
    await loginViaApi(page);
    await page.reload({ waitUntil: 'load' });
    await page.goto(`${BASE}/#/chat`, { waitUntil: 'load' });
    const field = page.locator('textarea').first();
    await field.waitFor({ state: 'visible', timeout: 20000 });
    await field.fill('在坐标(100, 64, 200)处放置一个钻石块');
    await page.waitForTimeout(500);
    await captureComposer(page, 'routing-preview-mobile-390.png');
    await context.close();
  }

  {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await page.goto(`${BASE}/`);
    await loginViaApi(page);
    await page.reload({ waitUntil: 'load' });
    await page.goto(`${BASE}/#/chat`, { waitUntil: 'load' });
    const field = page.locator('textarea').first();
    await field.waitFor({ state: 'visible', timeout: 20000 });
    await field.fill('在灵境精灵森林建造一座树桥聚落');
    await page.waitForTimeout(500);
    await page.locator('button.apple-send-btn').click();
    await page.waitForSelector('text=需求審計', { timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(OUT, 'routing-preview-grill-company.png'), fullPage: false });
    await context.close();
  }

  await browser.close();
  console.log('Saved screenshots to', OUT);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
