import type { ApiRoutePublic, LlmOpsData } from '../types';

export function isAuthCatalogError(message: string | undefined | null): boolean {
  const s = (message || '').toLowerCase();
  if (!s) return false;
  return (
    s.includes('401') ||
    s.includes('403') ||
    s.includes('unauthorized') ||
    s.includes('invalid api key') ||
    s.includes('incorrect api key') ||
    (s.includes('api key') && (s.includes('invalid') || s.includes('missing'))) ||
    s.includes('authentication')
  );
}

export type RouteProbeTone = 'disabled' | 'needsKey' | 'auth' | 'warn' | 'ok';

export function routeProbeTone(route: ApiRoutePublic): RouteProbeTone {
  if (!route.enabled) return 'disabled';
  if (!route.configured) return 'needsKey';
  if (route.catalog_error) {
    return isAuthCatalogError(route.catalog_error) ? 'auth' : 'warn';
  }
  return 'ok';
}

export function routeProbeDotClass(tone: RouteProbeTone): string {
  switch (tone) {
    case 'disabled':
      return 'bg-[#8E8E93]';
    case 'needsKey':
      return 'bg-[#FF9F0A]';
    case 'auth':
      return 'bg-[#FF453A]';
    case 'warn':
      return 'bg-[#FF9F0A]';
    default:
      return 'bg-[#30D158]';
  }
}

export function llmOpsHealthLabel(data: LlmOpsData | null): { text: string; tone: string } {
  const ops = data?.ops;
  if (!ops) return { text: '未知', tone: 'text-[var(--console-sub)]' };
  if (!ops.enabled) return { text: '定時任務已停用', tone: 'console-status-amber' };
  const routes = data?.api_routes ?? [];
  const anyAuth = routes.some((r) => r.enabled && r.configured && isAuthCatalogError(r.catalog_error));
  if (anyAuth || isAuthCatalogError(ops.last_error)) {
    return { text: '金鑰驗證失敗', tone: 'console-status-danger' };
  }
  if (ops.consecutive_fail >= 3) return { text: '連續失敗', tone: 'console-status-danger' };
  if (ops.stale) return { text: '目錄過期', tone: 'console-status-amber' };
  if (ops.last_error) return { text: '上次有錯，已回退', tone: 'console-status-amber' };
  const anyRouteWarn = routes.some((r) => r.enabled && r.configured && Boolean(r.catalog_error));
  if (anyRouteWarn) return { text: '部分路由需檢查', tone: 'console-status-amber' };
  return { text: '健康', tone: 'console-status-green' };
}

export function llmOpsShowLastError(ops: LlmOpsData['ops'] | undefined): boolean {
  if (!ops?.last_error) return false;
  if (isAuthCatalogError(ops.last_error)) return true;
  if ((ops.consecutive_fail ?? 0) > 0) return true;
  return Boolean(ops.stale);
}
