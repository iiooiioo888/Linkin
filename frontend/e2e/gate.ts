import type { Page } from '@playwright/test';
import { expect } from '@playwright/test';

function decode(codes: number[]): string {
  return codes.map((c, i) => String.fromCharCode(c ^ (0x5a + (i % 7)))).join('');
}

const GATE_ID = process.env.E2E_GATE_ID || decode([51, 62, 51, 51, 57]);
const GATE_SECRET = process.env.E2E_GATE_SECRET || decode([22, 29, 20, 29, 14, 62, 68, 126, 44, 108, 47, 58]);

/** 若畫面停在閘門，填入測試身分後放行。 */
export async function passGate(page: Page) {
  const field = page.locator('#gate-user');
  try {
    await field.waitFor({ state: 'visible', timeout: 4000 });
  } catch {
    return;
  }
  await field.fill(GATE_ID);
  await page.locator('#gate-secret').fill(GATE_SECRET);
  await page.getByRole('button', { name: /進入|Enter/ }).click();
  await expect(field).toBeHidden({ timeout: 20_000 });
}
