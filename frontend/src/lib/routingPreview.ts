import { fetchRoutingPreview } from '../api/client';
import type { CompanyTemplate, RoutingPreview, RoutingPreviewMode } from '../types';

/** 與 debounce 預覽請求對齊的上下文；發送時須完全一致才沿用 preview。 */
export interface RoutingPreviewSnapshot {
  query: string;
  mode: RoutingPreviewMode;
  companyTemplate: CompanyTemplate;
  preview: RoutingPreview;
}

export const ROUTING_PREVIEW_SEND_TIMEOUT_MS = 1500;

export function routingPreviewSnapshotMatches(
  snapshot: RoutingPreviewSnapshot | null | undefined,
  query: string,
  mode: RoutingPreviewMode,
  companyTemplate: CompanyTemplate,
): boolean {
  if (!snapshot?.preview) return false;
  const trimmed = query.trim();
  if (!trimmed || snapshot.query !== trimmed) return false;
  if (snapshot.mode !== mode) return false;
  if (mode === 'company' && snapshot.companyTemplate !== companyTemplate) return false;
  return true;
}

/** 發送前解析預覽：快照一致則沿用，否則重取（逾時不阻擋發送）。 */
export async function resolveRoutingPreviewForSend(params: {
  query: string;
  mode: RoutingPreviewMode;
  companyTemplate: CompanyTemplate;
  snapshot?: RoutingPreviewSnapshot | null;
}): Promise<RoutingPreview | null> {
  const trimmed = params.query.trim();
  if (!trimmed) return null;
  if (
    routingPreviewSnapshotMatches(
      params.snapshot,
      trimmed,
      params.mode,
      params.companyTemplate,
    )
  ) {
    return params.snapshot!.preview;
  }

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), ROUTING_PREVIEW_SEND_TIMEOUT_MS);
  try {
    return await fetchRoutingPreview(
      {
        query: trimmed,
        mode: params.mode,
        company_template: params.mode === 'company' ? params.companyTemplate : undefined,
      },
      controller.signal,
    );
  } catch {
    return null;
  } finally {
    window.clearTimeout(timer);
  }
}

/** 任務 API 路徑（非 SSE 簡單／minecraft_ops 串流）。opc 是舊標籤，與 company 同一條公司任務。 */
export function usesTaskWorkspace(
  strategy: RoutingPreviewMode,
  preview: RoutingPreview | null | undefined,
): boolean {
  if (strategy === 'simple') return false;
  if (strategy === 'company') return true;
  const path = preview?.path;
  return path === 'company' || path === 'opc';
}

/** 指揮鏈入口已移除。任務由任務經理在公司任務裡分析，對話不再先 Grill。 */
export function shouldRunGrill(
  _strategy: RoutingPreviewMode,
  _preview: RoutingPreview | null | undefined,
  _skipGrill?: boolean,
): boolean {
  return false;
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
