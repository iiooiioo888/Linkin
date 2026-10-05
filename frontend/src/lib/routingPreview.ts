import type { RoutingPreview, RoutingPreviewMode } from '../types';

/** 任務 API 路徑（非 SSE 簡單／minecraft_ops 串流）。 */
export function usesTaskWorkspace(
  strategy: RoutingPreviewMode,
  preview: RoutingPreview | null | undefined,
): boolean {
  if (strategy === 'simple') return false;
  if (strategy === 'company') return true;
  const path = preview?.path;
  return path === 'company' || path === 'opc';
}

/** 僅公司路徑進入需求審計官 Grill（對齊後端 should_grill_user）。 */
export function shouldRunGrill(
  strategy: RoutingPreviewMode,
  preview: RoutingPreview | null | undefined,
  skipGrill?: boolean,
): boolean {
  if (skipGrill || strategy === 'simple') return false;
  if (strategy === 'company') return true;
  return preview?.path === 'company';
}

export function parseRoutingPreview(data: Record<string, unknown>): RoutingPreview | null {
  const path = String(data.path ?? '').trim();
  if (path !== 'simple' && path !== 'company' && path !== 'opc' && path !== 'minecraft_ops') {
    return null;
  }
  const level = String((data.estimated_cost as { level?: string } | undefined)?.level ?? 'low');
  const estLevel =
    level === 'high' || level === 'medium' || level === 'low' ? level : 'low';
  const estTokens = Number((data.estimated_cost as { est_tokens?: number } | undefined)?.est_tokens ?? 0);
  return {
    path,
    template: data.template == null ? null : String(data.template),
    complexity: String(data.complexity ?? ''),
    tier: String(data.tier ?? ''),
    model_hint: String(data.model_hint ?? ''),
    max_reflection_rounds: Number(data.max_reflection_rounds ?? 0),
    reason_codes: Array.isArray(data.reason_codes)
      ? data.reason_codes.map((c) => String(c))
      : [],
    estimated_cost: {
      level: estLevel,
      est_tokens: Number.isFinite(estTokens) ? estTokens : 0,
    },
  };
}
