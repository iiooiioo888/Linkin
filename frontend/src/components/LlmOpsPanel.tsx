/**
 * LlmOpsPanel — 控制台「配置 → API 路由」。
 * 側欄列已配置 API；主區編輯金鑰／模型與目錄。用量與角色設定分屬計費／執行。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchLlmOps, refreshLlmModels, updateLlmOpsPrefs } from '../api/client';
import { extraRateItems, fmtPerMillion, fmtRate, lookupRateCard } from '../lib/agentUi';
import { navPathForTab } from '../lib/monitorTabs';
import type { LlmOpsData, ModelRateCard } from '../types';
import ApiRoutesEditor from './ApiRoutesEditor';

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

function rateField(data: LlmOpsData | null, modelId: string, field: keyof ModelRateCard): string {
  const card = lookupRateCard(modelId, data?.model_rate_cards);
  const n = card?.[field];
  if (typeof n !== 'number' || !n) return '—';
  return fmtPerMillion(n);
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
  const [pageTab, setPageTab] = useState<'edit' | 'catalog'>('edit');
  const [query, setQuery] = useState('');

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

  const groupedCatalog = useMemo(() => {
    const map = new Map<string, typeof filtered>();
    for (const m of filtered) {
      const key = m.route_name || '未歸組';
      const list = map.get(key) ?? [];
      list.push(m);
      map.set(key, list);
    }
    return [...map.entries()];
  }, [filtered]);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden apple-canvas text-[#f7f8f8]">
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-2 border-b border-white/[0.08] px-4 py-2.5">
        <div>
          <h2 className="text-sm font-semibold">API 路由</h2>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">
            多組 API 並存；每組再勾選可用模型。角色在「{navPathForTab('agents')} → 模型／設定」指定。
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
        <div className="mx-4 mt-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>
      )}

      <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b border-white/[0.06] px-4 py-2 text-[11px]">
        <span className={health.tone}>{health.text}</span>
        <span className="text-[#8a8f98]">
          {data?.api_routes?.length ?? 0} 組 API · {data?.allowed_models.length ?? 0} 模型 · {data?.route_strategy || 'role_preferred'}
        </span>
        <span className="text-[#636366]">{data?.lock_message}</span>
        <span className={`ml-auto ${ops?.stale ? 'text-amber-300' : 'text-[#636366]'}`}>
          下次 {fmtWhen(ops?.next_check_at)}
        </span>
        <span className="flex gap-1">
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
        </span>
      </div>

      {ops?.last_error && (
        <p className="shrink-0 px-4 pt-2 text-[12px] text-amber-200">
          上次錯誤：{ops.last_error}（連續失敗 {ops.consecutive_fail}）
        </p>
      )}

      <div className="flex shrink-0 gap-1 px-4 pt-3">
        {(
          [
            ['edit', '編輯'],
            ['catalog', `目錄 ${models.length}`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setPageTab(key)}
            className={`rounded-lg px-2.5 py-1 text-[12px] ${
              pageTab === key ? 'bg-[#007AFF]/20 text-[#64D2FF]' : 'text-[#8a8f98] hover:text-[#d0d6e0]'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {pageTab === 'edit' && (
          <div className="max-w-2xl">
            <ApiRoutesEditor hideList onChanged={() => void refresh()} />
            <p className="mt-4 text-[11px] text-[#636366]">
              下一步：到{' '}
              <a href="#/monitor/agents" className="text-[#64D2FF] hover:underline">
                {navPathForTab('agents')} → 模型／設定
              </a>
              {' '}為每個角色指定模型與 Token；用量見{' '}
              <a href="#/monitor/models" className="text-[#64D2FF] hover:underline">
                {navPathForTab('models')}
              </a>
              。
            </p>
          </div>
        )}

        {pageTab === 'catalog' && (
          <>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11px] text-[#8a8f98]">目前預設 {data?.model || '—'}</p>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜尋模型 ID / 名稱 / API"
                className="w-56 rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#d0d6e0] placeholder:text-[#62666d]"
              />
            </div>
            <div className="overflow-x-auto rounded-lg border border-white/[0.08]">
              <table className="w-full text-left text-[12px]">
                <thead className="bg-[#1C1C1E] text-[10px] uppercase tracking-wider text-[#62666d]">
                  <tr>
                    <th className="px-3 py-2 font-medium">模型 ID</th>
                    <th className="px-3 py-2 font-medium">名稱</th>
                    <th className="px-3 py-2 font-medium">API</th>
                    <th className="px-3 py-2 font-medium">輸入</th>
                    <th className="px-3 py-2 font-medium">輸出</th>
                    <th className="px-3 py-2 font-medium">收費項</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-3 py-8 text-center text-[#62666d]">
                        {models.length === 0
                          ? '尚無目錄。在左側加入千問／DeepSeek／Kimi／OpenRouter 後按「立刻檢查目錄」。'
                          : '沒有符合搜尋的模型'}
                      </td>
                    </tr>
                  ) : (
                    groupedCatalog.flatMap(([group, rows]) =>
                      rows.slice(0, 80).map((m, idx) => (
                        <tr key={`${group}-${m.id}`} className="border-t border-white/[0.08]">
                          <td className="px-3 py-1.5 font-mono text-[#d0d6e0]">
                            {m.id}
                            {m.id === data?.model ? (
                              <span className="ml-2 text-[10px] text-[#64D2FF]">預設</span>
                            ) : null}
                          </td>
                          <td className="px-3 py-1.5 text-[#8a8f98]">{m.name}</td>
                          <td className="px-3 py-1.5 text-[#8a8f98]">
                            {idx === 0 || rows[idx - 1]?.route_name !== m.route_name ? group : ''}
                          </td>
                          <td className="px-3 py-1.5 font-mono text-[#8a8f98]">{rateField(data, m.id, 'input')}</td>
                          <td className="px-3 py-1.5 font-mono text-[#8a8f98]">{rateField(data, m.id, 'output')}</td>
                          <td className="px-3 py-1.5">
                            <div className="flex flex-wrap gap-1">
                              {extraRateItems(lookupRateCard(m.id, data?.model_rate_cards)).length === 0 ? (
                                <span className="text-[#62666d]">—</span>
                              ) : (
                                extraRateItems(lookupRateCard(m.id, data?.model_rate_cards)).map((item) => (
                                  <span
                                    key={item.id}
                                    className="rounded bg-white/[0.04] px-1.5 py-0.5 font-mono text-[10px] text-[#AEAEB2]"
                                  >
                                    {item.label} {fmtRate(item.usd_per_1m, item.unit)}
                                  </span>
                                ))
                              )}
                            </div>
                          </td>
                        </tr>
                      )),
                    )
                  )}
                </tbody>
              </table>
            </div>
            {filtered.length > 80 && (
              <p className="mt-2 text-[11px] text-[#62666d]">僅顯示前 80 筆／組，請用搜尋縮小範圍。</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
