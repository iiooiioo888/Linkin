import type { LlmCatalogModel } from '../types';

export const TOKEN_PLAN_LABEL = '阿里雲 Token Plan';

export const MODEL_FAMILY_LABELS: Record<string, string> = {
  qwen: '通義千問 Qwen',
  deepseek: 'DeepSeek',
  zhipu: '智譜 GLM',
  moonshot: 'Moonshot / Kimi',
  'token-plan': TOKEN_PLAN_LABEL,
};

export function isTokenPlanUrl(url: string | undefined): boolean {
  return (url || '').toLowerCase().includes('token-plan');
}

export function familyLabel(family: string | undefined): string {
  if (!family) return '';
  return MODEL_FAMILY_LABELS[family] || family;
}

/** 目錄分組：Token Plan 依 owned_by 拆成 route · family */
export function catalogGroupKey(model: LlmCatalogModel): string {
  const route = model.route_name || '';
  const family = model.owned_by || '';
  if (route && family && family !== 'token-plan') {
    return `${route} · ${familyLabel(family)}`;
  }
  return route || familyLabel(family) || '未歸組';
}

export function modelsForRoute(
  groups: Array<{ route_id: string; models: string[] }>,
  routeId: string,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const group of groups) {
    if (group.route_id !== routeId) continue;
    for (const mid of group.models) {
      if (!mid || seen.has(mid)) continue;
      seen.add(mid);
      out.push(mid);
    }
  }
  return out;
}
