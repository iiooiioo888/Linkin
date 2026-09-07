/**
 * LlmOpsPanel — 控制台「系統 → API 路由」。
 * 左：多 API 配置；右：健康快照與模型目錄。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchLlmOps, refreshLlmModels, updateLlmOpsPrefs } from '../api/client';
import type { LlmOpsData } from '../types';
import ApiRoutesEditor from './ApiRoutesEditor';
import OptimizationPanel from './OptimizationPanel';

function fmtWhen(iso: string | undefined): string {
  if (!iso) return '尚未檢查';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('zh-TW', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function healthLabel(data: LlmOpsData | null): { text: string; tone: string } {
  const ops = data?.ops;
  if (!ops) return { text: '未知', tone: 'text-[#8a8f98]' };
  if (!ops.enabled) return { text: '定時任務已停用', tone: 'text-amber-300' };
  if (ops.consecutive_fail >= 3) return { text: '連續失敗', tone: 'text-red-300' };
  if (ops.stale) return { text: '目錄過期', tone: 'text-amber-300' };
  if (ops.last_error) return { text: '上次有錯，已回退', tone: 'text-amber-200' };
  return { text: '健康', tone: 'text-[#4cc38a]' };
}

export default function LlmOpsPanel() {
  const [data, setData] = useState<LlmOpsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState('');
  const [showCatalog, setShowCatalog] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchLlmOps();
      setData(next);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 8000);
    return () => clearInterval(timer);
  }, [refresh]);

  const ops = data?.ops;
  const models = data?.catalog ?? [];
  const health = healthLabel(data);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return models;
    return models.filter(
      (m) =>
        m.id.toLowerCase().includes(q) ||
        (m.name || '').toLowerCase().includes(q) ||
        (m.owned_by || '').toLowerCase().includes(q) ||
        (m.route_name || '').toLowerCase().includes(q),
    );
  }, [models, query]);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto apple-canvas p-4 text-[#f7f8f8]">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">API 路由</h2>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">
            多組 API 並存（千問／DeepSeek／Kimi／OpenRouter）。角色在「執行 → 角色 → 模型／路由」指定模型與 Token。
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const next = await refreshLlmModels();
                setData(next);
                setError(null);
              } catch (err) {
                setError((err as Error).message);
              } finally {
                setBusy(false);
              }
            }}
            className="rounded-md border border-[#007AFF]/40 bg-[#007AFF]/15 px-2 py-1 text-[11px] text-[#64D2FF] disabled:opacity-40"
          >
            {busy ? '爬取中…' : '立刻檢查目錄'}
          </button>
          <button
            type="button"
            onClick={() => void refresh()}
            className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#8a8f98]"
          >
            重新整理
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-2 lg:grid-cols-5">
        <div className="apple-card apple-card--tight !p-0 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-wider text-[#62666d]">供應商鎖定</p>
          <p className="mt-1 text-sm text-[#f7f8f8]">{data?.provider_label ?? '—'}</p>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">{data?.lock_message}</p>
        </div>
        <div className="apple-card apple-card--tight !p-0 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-wider text-[#62666d]">健康</p>
          <p className={`mt-1 text-sm ${health.tone}`}>{health.text}</p>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">
            來源 {data?.catalog_source || '—'} · 原因 {ops?.last_reason || '—'}
          </p>
        </div>
        <div className="apple-card apple-card--tight !p-0 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-wider text-[#62666d]">可用模型</p>
          <p className="mt-1 font-mono text-lg text-[#f7f8f8]">{data?.allowed_models.length ?? 0}</p>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">
            {data?.api_routes?.length ?? 0} 組 API · 策略 {data?.route_strategy || 'role_preferred'}
          </p>
        </div>
        <div className="apple-card apple-card--tight !p-0 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-wider text-[#62666d]">最近 / 下次檢查</p>
          <p className="mt-1 text-sm text-[#f7f8f8]">{fmtWhen(ops?.last_ok_at || data?.catalog_fetched_at)}</p>
          <p className={`mt-0.5 text-[11px] ${ops?.stale ? 'text-amber-300' : 'text-[#8a8f98]'}`}>
            下次 {fmtWhen(ops?.next_check_at)} · {ops?.last_latency_ms ?? 0} ms
          </p>
        </div>
        <div className="apple-card apple-card--tight !p-0 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-wider text-[#62666d]">定時間隔</p>
          <p className="mt-1 font-mono text-lg text-[#f7f8f8]">{ops?.refresh_interval_sec ?? 300}s</p>
          <div className="mt-1 flex flex-wrap gap-1">
            {[60, 300, 900].map((sec) => (
              <button
                key={sec}
                type="button"
                className={`rounded px-1.5 py-0.5 text-[10px] ${
                  ops?.refresh_interval_sec === sec ? 'bg-[#007AFF]/20 text-[#64D2FF]' : 'text-[#8a8f98]'
                }`}
                onClick={() => void updateLlmOpsPrefs(sec).then(setData)}
              >
                {sec >= 60 ? `${sec / 60} 分` : `${sec}s`}
              </button>
            ))}
          </div>
        </div>
      </div>

      {ops?.last_error && (
        <p className="mb-3 text-[12px] text-amber-200">
          上次錯誤：{ops.last_error}（連續失敗 {ops.consecutive_fail}）
        </p>
      )}

      <div className="grid min-h-0 grid-cols-1 gap-4 xl:grid-cols-12">
        <section className="xl:col-span-5">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[#62666d]">配置</p>
          <ApiRoutesEditor onChanged={() => void refresh()} />
        </section>

        <section className="xl:col-span-7">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => setShowCatalog((v) => !v)}
              className="text-[10px] font-semibold uppercase tracking-wider text-[#62666d] hover:text-[#AEAEB2]"
            >
              {showCatalog ? '▾' : '▸'} 模型目錄 · 目前預設 {data?.model || '—'}
            </button>
            <div className="flex items-center gap-2">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜尋模型 ID / 名稱 / API"
                className="w-48 rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#d0d6e0] placeholder:text-[#62666d]"
              />
              <p className="hidden text-[10px] text-[#62666d] lg:block">{data?.catalog_url}</p>
            </div>
          </div>
          {showCatalog && (
            <>
              <div className="overflow-hidden rounded-lg border border-white/[0.08]">
                <table className="w-full text-left text-[12px]">
                  <thead className="bg-[#1C1C1E] text-[10px] uppercase tracking-wider text-[#62666d]">
                    <tr>
                      <th className="px-3 py-2 font-medium">模型 ID</th>
                      <th className="px-3 py-2 font-medium">名稱</th>
                      <th className="px-3 py-2 font-medium">owned_by</th>
                      <th className="px-3 py-2 font-medium">API</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-3 py-8 text-center text-[#62666d]">
                          {models.length === 0
                            ? '尚無目錄。在左側加入千問／DeepSeek／Kimi／OpenRouter 後按「立刻檢查目錄」。'
                            : '沒有符合搜尋的模型'}
                        </td>
                      </tr>
                    ) : (
                      filtered.slice(0, 120).map((m) => (
                        <tr key={`${m.route_name || ''}-${m.id}`} className="border-t border-white/[0.08]">
                          <td className="px-3 py-1.5 font-mono text-[#d0d6e0]">
                            {m.id}
                            {m.id === data?.model ? (
                              <span className="ml-2 text-[10px] text-[#64D2FF]">預設</span>
                            ) : null}
                          </td>
                          <td className="px-3 py-1.5 text-[#8a8f98]">{m.name}</td>
                          <td className="px-3 py-1.5 text-[#62666d]">{m.owned_by || '—'}</td>
                          <td className="px-3 py-1.5 text-[#8a8f98]">{m.route_name || '—'}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
              {filtered.length > 120 && (
                <p className="mt-2 text-[11px] text-[#62666d]">僅顯示前 120 筆，請用搜尋縮小範圍。</p>
              )}
            </>
          )}
          <OptimizationPanel />
        </section>
      </div>
    </div>
  );
}
