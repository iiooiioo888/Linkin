/**
 * API 路由編輯器：已配置的 API 清單（含編輯／目錄／測試／刪除）。
 */
import type { ApiRoutePublic } from '../../types';

interface RouteListProps {
  hideList: boolean;
  routes: ApiRoutePublic[];
  editingId: string | null;
  startEdit: (route: ApiRoutePublic) => void;
  handleRefresh: (routeId?: string) => Promise<void>;
  handleTest: (routeId: string) => Promise<void>;
  handleDelete: (routeId: string) => Promise<void>;
}

export function RouteList({
  hideList,
  routes,
  editingId,
  startEdit,
  handleRefresh,
  handleTest,
  handleDelete,
}: RouteListProps) {
  return hideList ? (
    <p className="text-[11px] text-[var(--console-sub)]">
      左側清單點選編輯；此處新增或修改金鑰與可用模型。
    </p>
  ) : (
    <div className="space-y-2">
      <p className="text-[10px] font-semibold text-[var(--console-sub)]">已配置的 API</p>
      {routes.length === 0 ? (
        <p className="rounded-xl border border-dashed border-white/[0.08] px-3 py-6 text-center text-sm text-[var(--console-sub)]">
          尚未加入 API。請在下方選擇供應商並填入金鑰。
        </p>
      ) : (
        routes.map((route) => (
          <div
            key={route.id}
            className={`rounded-xl border px-3 py-2 ${
              editingId === route.id
                ? 'border-[color-mix(in_srgb,var(--console-accent)_40%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)]'
                : 'border-white/[0.08] bg-white/[0.02]'
            }`}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm text-[var(--console-ink)]">
                  {route.name}
                  {route.is_default ? <span className="ml-2 text-[10px] text-[var(--console-accent)]">預設</span> : null}
                  {!route.enabled ? <span className="ml-2 text-[10px] text-[var(--console-amber)]">停用</span> : null}
                  {route.fallback ? <span className="ml-2 text-[10px] text-[var(--console-sub)]">備援</span> : null}
                </p>
                <p className="text-[11px] text-[var(--console-sub)]">
                  {route.provider_label} · {route.model || '未指定預設模型'} · {route.allowed_models.length} 個模型
                  {route.configured ? ` · ${route.api_key}` : ' · 未設金鑰'}
                  {route.models_locked ? ' · 已鎖定模型清單' : ''}
                </p>
                {route.allowed_models.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {route.allowed_models.slice(0, 8).map((mid) => (
                      <span
                        key={mid}
                        className="rounded border border-white/[0.08] bg-[var(--console-card)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--console-sub)]"
                      >
                        {mid}
                      </span>
                    ))}
                    {route.allowed_models.length > 8 ? (
                      <span className="text-[10px] text-[var(--console-sub)]">+{route.allowed_models.length - 8}</span>
                    ) : null}
                  </div>
                )}
              </div>
              <div className="flex flex-wrap gap-1">
                <button
                  type="button"
                  className="rounded-lg border border-white/[0.08] px-2 py-0.5 text-[11px] text-[var(--console-sub)] hover:bg-white/[0.04]"
                  onClick={() => startEdit(route)}
                >
                  編輯
                </button>
                <button
                  type="button"
                  className="rounded-lg border border-white/[0.08] px-2 py-0.5 text-[11px] text-[var(--console-sub)] hover:bg-white/[0.04]"
                  onClick={() => void handleRefresh(route.id)}
                >
                  目錄
                </button>
                <button
                  type="button"
                  className="rounded-lg border border-white/[0.08] px-2 py-0.5 text-[11px] text-[var(--console-sub)] hover:bg-white/[0.04]"
                  onClick={() => void handleTest(route.id)}
                >
                  測試
                </button>
                <button
                  type="button"
                  className="rounded-lg border border-[color-mix(in_srgb,var(--console-danger)_30%,transparent)] px-2 py-0.5 text-[11px] text-[var(--console-danger)] hover:bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)]"
                  onClick={() => void handleDelete(route.id)}
                >
                  刪除
                </button>
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
