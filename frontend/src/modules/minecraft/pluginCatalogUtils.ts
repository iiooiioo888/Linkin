/** 插件目錄 API 欄位正規化（platforms 偶爾為 JSON 字串而非陣列）。 */

export function normalizeStringList(value: unknown): string[] {
  if (value == null) return [];
  if (Array.isArray(value)) {
    return value.map((v) => String(v).trim()).filter((s) => s.length > 0);
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed ? [trimmed] : [];
  }
  const text = String(value).trim();
  return text ? [text] : [];
}

export function formatPlatformsLabel(value: unknown): string {
  const list = normalizeStringList(value);
  return list.length > 0 ? list.join(' · ') : '—';
}
