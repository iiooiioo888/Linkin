import type { Page } from '@playwright/test';
import { expect } from '@playwright/test';

/**
 * E2E 閘門放行：身分只從環境變數讀取，倉庫不放來源值。
 * 本機請設 E2E_GATE_ID / E2E_GATE_SECRET。
 */
export async function passGate(page: Page) {
  const field = page.locator('#gate-user');
  try {
    await field.waitFor({ state: 'visible', timeout: 4000 });
  } catch {
    return;
  }
  const id = (process.env.E2E_GATE_ID || '').trim();
  const secret = process.env.E2E_GATE_SECRET || '';
  if (!id || !secret) {
    throw new Error('E2E 閘門可見，但未設定 E2E_GATE_ID / E2E_GATE_SECRET');
  }
  await field.fill(id);
  await page.locator('#gate-secret').fill(secret);
  await page.getByRole('button', { name: /進入|Enter/ }).click();
  await expect(field).toBeHidden({ timeout: 20_000 });
}
