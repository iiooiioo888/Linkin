import type { Page } from '@playwright/test';
import { expect } from '@playwright/test';

const GATE_ID = process.env.E2E_GATE_ID ?? '';
const GATE_SECRET = process.env.E2E_GATE_SECRET ?? '';

/** 若畫面停在閘門，填入測試身分後放行。身分只來自環境變數。 */
export async function passGate(page: Page) {
  const field = page.locator('#gate-user');
  try {
    await field.waitFor({ state: 'visible', timeout: 4000 });
  } catch {
    return;
  }
  if (!GATE_ID || !GATE_SECRET) {
    throw new Error('E2E_GATE_ID 與 E2E_GATE_SECRET 必須設定');
  }
  await field.fill(GATE_ID);
  await page.locator('#gate-secret').fill(GATE_SECRET);
  await page.getByRole('button', { name: /登入|Sign in/ }).click();
  await expect(field).toBeHidden({ timeout: 20_000 });
}
