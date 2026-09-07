/**
 * LightningChart JS 單例工廠。無授權時降級為 Canvas，避免控制台空白。
 * 部署金鑰：VITE_LCJS_LICENSE（社群／開發授權皆可）。
 */
import type { LightningChart, Theme } from '@lightningchart/lcjs';

type LcModule = typeof import('@lightningchart/lcjs');

let factory: LightningChart | null | undefined;
let cached: LcModule | null = null;

export async function loadLcjs(): Promise<LcModule | null> {
  if (cached) return cached;
  try {
    cached = await import('@lightningchart/lcjs');
    return cached;
  } catch (err) {
    console.warn('[lcjs] 模組載入失敗', err);
    return null;
  }
}

export async function getLcFactory(): Promise<LightningChart | null> {
  if (factory !== undefined) return factory;
  const mod = await loadLcjs();
  if (!mod) {
    factory = null;
    return null;
  }
  try {
    const license = import.meta.env.VITE_LCJS_LICENSE?.trim();
    factory = license ? mod.lightningChart({ license }) : mod.lightningChart();
    return factory;
  } catch (err) {
    console.warn('[lcjs] 初始化失敗（多半缺授權），改用 Canvas 後備', err);
    factory = null;
    return null;
  }
}

export async function darkTheme(): Promise<Theme | null> {
  const mod = await loadLcjs();
  return mod?.Themes.darkGold ?? null;
}
