/** 將 API／store 的比率正規化為 0–100 數字（剝除尾端 % 與非數字）。 */
export function normalizePercentNumber(value: unknown): number | null {
  if (value == null) return null;
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }
  const raw = String(value).trim();
  if (!raw || raw === '—') return null;
  const cleaned = raw.replace(/%+$/u, '').replace(/[^\d.-]/gu, '');
  if (!cleaned) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

/** 顯示用百分比字串（僅一個 %）。 */
export function formatPercentLabel(value: unknown, fallback = '0'): string {
  const n = normalizePercentNumber(value);
  if (n == null) return `${fallback}%`;
  return `${n}%`;
}

/** KPI 卡片：數值與 unit 分開時用（避免 value 已含 % 又傳 unit="%")。 */
export function formatPercentKpiParts(value: unknown): { value: string; unit?: string } {
  const n = normalizePercentNumber(value);
  if (n == null) return { value: '—' };
  return { value: String(n), unit: '%' };
}
