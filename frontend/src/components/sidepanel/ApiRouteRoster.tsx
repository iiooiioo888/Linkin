/**
 * SidePanel 已配置 API 路由名冊。
 */
import { useEffect, useState } from 'react';
import { fetchLlmOps } from '../../api/client';
import {
  API_ROUTES_CHANGED_EVENT,
  dispatchEditApiRoute,
  dispatchNewApiRoute,
  EDIT_API_ROUTE_EVENT,
  NEW_API_ROUTE_EVENT,
} from '../../lib/agentUi';
import { routeProbeDotClass, routeProbeTone } from '../../lib/llmOpsHealth';
import type { ApiRoutePublic } from '../../types';

export function ApiRouteRoster() {
  const [routes, setRoutes] = useState<ApiRoutePublic[]>([]);
  const [strategy, setStrategy] = useState('role_preferred');
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    const load = () =>
      fetchLlmOps()
        .then((ops) => {
          setRoutes(ops.api_routes ?? []);
          setStrategy(ops.route_strategy || 'role_preferred');
        })
        .catch(() => {
          setRoutes([]);
        });
    void load();
    const timer = setInterval(() => void load(), 8000);
    window.addEventListener(API_ROUTES_CHANGED_EVENT, load);
    const onEdit = (e: Event) => setActiveId((e as CustomEvent<string>).detail || null);
    const onNew = () => setActiveId(null);
    window.addEventListener(EDIT_API_ROUTE_EVENT, onEdit);
    window.addEventListener(NEW_API_ROUTE_EVENT, onNew);
    return () => {
      clearInterval(timer);
      window.removeEventListener(API_ROUTES_CHANGED_EVENT, load);
      window.removeEventListener(EDIT_API_ROUTE_EVENT, onEdit);
      window.removeEventListener(NEW_API_ROUTE_EVENT, onNew);
    };
  }, []);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 space-y-1.5 border-b border-white/[0.06] px-3 pb-3 pt-2">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[10px] font-bold text-[var(--console-sub)]">已配置的 API</p>
          <button
            type="button"
            onClick={() => dispatchNewApiRoute()}
            className="rounded-md px-1.5 py-0.5 text-[10px] text-[var(--console-accent)] hover:bg-white/[0.06]"
          >
            新增
          </button>
        </div>
        <p className="text-[10px] text-[var(--console-sub)]">
          {routes.length} 組 · 策略 {strategy}
        </p>
      </div>
      {routes.length === 0 ? (
        <p className="px-3 py-8 text-center text-[11px] text-[var(--console-sub)]">
          尚未加入 API。請在右側選擇供應商並填入金鑰。
        </p>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
          {routes.map((route) => (
            <button
              key={route.id}
              type="button"
              onClick={() => dispatchEditApiRoute(route.id)}
              className={`mx-1.5 mb-0.5 flex w-[calc(100%-12px)] items-center gap-2 rounded-lg px-2.5 py-1.5 text-left ${
                activeId === route.id
                  ? 'bg-white/[0.06] text-[var(--console-ink)]'
                  : 'text-[var(--console-sub)] hover:bg-white/[0.03] hover:text-[var(--console-ink)]'
              }`}
            >
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${routeProbeDotClass(routeProbeTone(route))}`}
                title={
                  route.catalog_error
                    ? route.catalog_error
                    : !route.configured
                      ? '未設金鑰'
                      : route.enabled
                        ? '已啟用'
                        : '已停用'
                }
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12px] font-medium text-[var(--console-ink)]">
                  {route.name}
                  {route.is_default ? <span className="ml-1 text-[9px] text-[var(--console-accent)]">預設</span> : null}
                </span>
                <span className="block truncate text-[10px] text-[var(--console-sub)]">
                  {route.provider_label || route.provider} · {route.allowed_models.length} 模型
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
