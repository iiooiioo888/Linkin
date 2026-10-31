/**
 * G-MAP1 路徑 B sunset／unsupported_long_term 九鍵（產品 UI 隱藏用）。
 *
 * 隱藏 ≠ 改 hub_id_map／sunset ≠ 改 WIRE／後端閘。
 * 直打 API 仍走閘拒；歷史 Trace 可仍顯示這些 id。
 */

export const SUNSET_HUB_IDS = [
  'gpt-5.6-sol',
  'gemini-3.1-pro',
  'mimo-v2.5-pro',
  'deepseek-v4-flash',
  'qwen3.8-max',
  'mercury-2',
  'nemotron-3.5-lightning',
  'glm-5.3',
  'kimi-k3',
] as const;

export type SunsetHubId = (typeof SUNSET_HUB_IDS)[number];

const SUNSET_SET: ReadonlySet<string> = new Set(SUNSET_HUB_IDS);

/** 是否為路徑 B sunset 九鍵之一（大小寫敏感，與 map id 對齊）。 */
export function isSunsetHubId(id: string | null | undefined): boolean {
  if (!id) return false;
  return SUNSET_SET.has(id.trim());
}

/** 自可選清單剔除 sunset 九鍵（保留順序）。 */
export function filterSelectableHubIds<T extends string>(ids: readonly T[]): T[] {
  return ids.filter((id) => !isSunsetHubId(id));
}

/** 物件清單（需有 id）剔除 sunset；用於 Hub 選型下拉。 */
export function filterSelectableHubModels<T extends { id: string }>(models: readonly T[]): T[] {
  return models.filter((m) => !isSunsetHubId(m.id));
}

/**
 * 監控／fallback 目錄：sunset 標記不可用（仍可展示歷史／目錄列），
 * 不刪列，避免監控空白；選型面請另用 filterSelectable*。
 */
export function markSunsetHubModelsUnavailable<T extends { id: string; available_in_pool?: boolean }>(
  models: readonly T[],
): T[] {
  return models.map((m) =>
    isSunsetHubId(m.id) ? { ...m, available_in_pool: false } : m,
  );
}

/** 收集 draft 內仍指向 sunset 的欄位（preferred／failover），供拒送出文案。 */
export function collectSunsetModelRefs(input: {
  preferred_model?: string | null;
  failover_models?: readonly string[] | null;
}): string[] {
  const hits: string[] = [];
  const preferred = (input.preferred_model ?? '').trim();
  if (isSunsetHubId(preferred)) hits.push(preferred);
  for (const raw of input.failover_models ?? []) {
    const id = String(raw ?? '').trim();
    if (isSunsetHubId(id) && !hits.includes(id)) hits.push(id);
  }
  return hits;
}

export const SUNSET_BLOCK_MESSAGE =
  '指定模型或故障轉移含已 sunset／unsupported_long_term 的 Hub 鍵，請改選可用模型後再儲存。';
