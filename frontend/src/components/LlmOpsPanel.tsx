/**
 * LlmOpsPanel — 控制台「配置 → API 路由」。
 * 側欄列已配置 API；主區編輯金鑰／模型與目錄。用量與角色設定分屬計費／執行。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchLlmOps, refreshLlmModels, updateLlmOpsPrefs } from '../api/client';
import { extraRateItems, fmtPerMillion, fmtRate, lookupRateCard } from '../lib/agentUi';
import { catalogGroupKey, familyLabel } from '../lib/llmCatalog';
import { navPathForTab } from '../lib/monitorTabs';
import type { LlmOpsData, ModelRateCard } from '../types';
import ApiRoutesEditor from './ApiRoutesEditor';
import {
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  ConsoleLeftRail,
  ConsoleRailNav,
  ConsoleRightRail,
  ConsoleSnippetList,
  ConsoleThreeColumn,
  PanelAlert,
  PanelShell,
  SectionHeader,
  consoleLayout,
} from './ui/ConsoleLayout';

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
  if (!ops) return { text: '未知', tone: 'text-[var(--console-sub)]' };
  if (!ops.enabled) return { text: '定時任務已停用', tone: 'console-status-amber' };
  if (ops.consecutive_fail >= 3) return { text: '連續失敗', tone: 'console-status-danger' };
  if (ops.stale) return { text: '目錄過期', tone: 'console-status-amber' };
  if (ops.last_error) return { text: '上次有錯，已回退', tone: 'console-status-amber' };
  return { text: '健康', tone: 'console-status-green' };
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
        familyLabel(m.owned_by).toLowerCase().includes(q) ||
        (m.route_name || '').toLowerCase().includes(q) ||
        catalogGroupKey(m).toLowerCase().includes(q),
    );
  }, [models, query]);

  const groupedCatalog = useMemo(() => {
    const map = new Map<string, typeof filtered>();
    for (const m of filtered) {
      const key = catalogGroupKey(m);
      const list = map.get(key) ?? [];
      list.push(m);
      map.set(key, list);
    }
    return [...map.entries()];
  }, [filtered]);

  const LLM_SECTIONS = [
    { id: 'llm-edit', key: 'edit' as const, label: '編輯路由' },
    { id: 'llm-catalog', key: 'catalog' as const, label: `目錄 ${models.length}` },
  ];
  const activeId = LLM_SECTIONS.find((s) => s.key === pageTab)?.id ?? LLM_SECTIONS[0].id;

  return (
    <PanelShell scroll={false}>
      <ConsoleThreeColumn>
        <ConsoleLeftRail>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-4">
            <h1 className="text-[15px] font-semibold text-[var(--console-ink)]">API 路由</h1>
            <p className="mt-1 text-[10px] text-[var(--console-faint)]">多組 API · 模型目錄</p>
          </div>
          <ConsoleColumnScroll className="!px-0 !py-0">
            <ConsoleRailNav
              sections={LLM_SECTIONS.map((s) => ({ id: s.id, label: s.label }))}
              activeId={activeId}
              onSelect={(id) => {
                const next = LLM_SECTIONS.find((s) => s.id === id);
                if (next) setPageTab(next.key);
              }}
            />
          </ConsoleColumnScroll>
        </ConsoleLeftRail>

        <ConsoleCenterColumn>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-3">
            <SectionHeader
              title={pageTab === 'edit' ? '編輯路由' : '模型目錄'}
              description={`多組 API 並存；每組再勾選可用模型。角色在「${navPathForTab('agents')} → 模型／設定」指定。`}
              actions={
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
                    className="rounded-md border border-[color-mix(in_srgb,var(--console-blue)_40%,transparent)] bg-[color-mix(in_srgb,var(--console-blue)_15%,transparent)] px-2 py-1 text-[11px] console-status-blue disabled:opacity-40"
                  >
                    {busy ? '爬取中…' : '立刻檢查目錄'}
                  </button>
                  <button type="button" onClick={() => void refresh()} className={consoleLayout.refreshBtn}>
                    重新整理
                  </button>
                </div>
              }
            />
            {error ? <PanelAlert className="mt-2">{error}</PanelAlert> : null}
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
              <span className={health.tone}>{health.text}</span>
              <span className="text-[var(--console-sub)]">
                {data?.api_routes?.length ?? 0} 組 API · {data?.allowed_models.length ?? 0} 模型 ·{' '}
                {data?.route_strategy || 'role_preferred'}
              </span>
            </div>
          </div>
          <ConsoleColumnScroll>
            {pageTab === 'edit' && (
              <div className="max-w-2xl">
                <ApiRoutesEditor hideList onChanged={() => void refresh()} />
                <p className="mt-4 text-[11px] text-[var(--console-faint)]">
                  下一步：到{' '}
                  <a href="#/monitor/agents" className="console-status-blue hover:underline">
                    {navPathForTab('agents')} → 模型／設定
                  </a>{' '}
                  為每個角色指定模型與 Token；用量見{' '}
                  <a href="#/monitor/models" className="console-status-blue hover:underline">
                    {navPathForTab('models')}
                  </a>
                  。
                </p>
              </div>
            )}

            {pageTab === 'catalog' && (
              <>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[11px] text-[var(--console-sub)]">目前預設 {data?.model || '—'}</p>
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="搜尋模型 ID / 名稱 / API"
                    className="w-56 rounded-lg border border-[var(--console-line)] bg-[var(--console-card)] px-2 py-1 text-[11px] text-[var(--console-ink)] placeholder:text-[var(--console-faint)]"
                  />
                </div>
                <div className="overflow-x-auto rounded-lg border border-[var(--console-line)]">
                  <table className="w-full text-left text-[12px]">
                    <thead className="bg-[var(--console-card-elevated)] text-[10px] uppercase tracking-wider text-[var(--console-faint)]">
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
                          <td colSpan={6} className="px-3 py-8 text-center text-[var(--console-faint)]">
                            {models.length === 0
                              ? '尚無目錄。在左側加入千問／DeepSeek／Kimi／OpenRouter 後按「立刻檢查目錄」。'
                              : '沒有符合搜尋的模型'}
                          </td>
                        </tr>
                      ) : (
                        groupedCatalog.flatMap(([group, rows]) =>
                          rows.slice(0, 80).map((m, idx) => (
                            <tr key={`${group}-${m.id}`} className="border-t border-[var(--console-line)]">
                              <td className="px-3 py-1.5 font-mono text-[var(--console-sub)]">
                                {m.id}
                                {m.id === data?.model ? (
                                  <span className="ml-2 text-[10px] console-status-blue">預設</span>
                                ) : null}
                              </td>
                              <td className="px-3 py-1.5 text-[var(--console-sub)]">
                                {m.name !== m.id ? m.name : '—'}
                                {m.owned_by && m.owned_by !== 'token-plan' ? (
                                  <span className="ml-1 text-[10px] text-[var(--console-faint)]">
                                    ({familyLabel(m.owned_by)})
                                  </span>
                                ) : null}
                              </td>
                              <td className="px-3 py-1.5 text-[var(--console-sub)]">
                                {idx === 0 ? group : ''}
                              </td>
                              <td className="px-3 py-1.5 font-mono text-[var(--console-sub)]">
                                {rateField(data, m.id, 'input')}
                              </td>
                              <td className="px-3 py-1.5 font-mono text-[var(--console-sub)]">
                                {rateField(data, m.id, 'output')}
                              </td>
                              <td className="px-3 py-1.5">
                                <div className="flex flex-wrap gap-1">
                                  {extraRateItems(lookupRateCard(m.id, data?.model_rate_cards)).length === 0 ? (
                                    <span className="text-[var(--console-faint)]">—</span>
                                  ) : (
                                    extraRateItems(lookupRateCard(m.id, data?.model_rate_cards)).map((item) => (
                                      <span
                                        key={item.id}
                                        className="rounded bg-[color-mix(in_srgb,var(--console-ink)_4%,transparent)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--console-sub)]"
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
                  <p className="mt-2 text-[11px] text-[var(--console-faint)]">僅顯示前 80 筆／組，請用搜尋縮小範圍。</p>
                )}
              </>
            )}
          </ConsoleColumnScroll>
        </ConsoleCenterColumn>

        <ConsoleRightRail>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-3">
            <p className="text-[11px] font-semibold text-[var(--console-ink)]">目錄健康</p>
          </div>
          <ConsoleColumnScroll>
            <div className={consoleLayout.sectionStack}>
              <ConsoleSnippetList title="狀態">
                <div className={consoleLayout.snippetRow}>
                  <span>探針</span>
                  <span className={health.tone}>{health.text}</span>
                </div>
                <div className={consoleLayout.snippetRow}>
                  <span>下次檢查</span>
                  <span className={ops?.stale ? 'console-status-amber' : 'text-[var(--console-sub)]'}>
                    {fmtWhen(ops?.next_check_at)}
                  </span>
                </div>
              </ConsoleSnippetList>
              {ops?.last_error ? (
                <ConsoleSnippetList title="上次錯誤">
                  <p className="text-[11px] console-status-amber">{ops.last_error}</p>
                  <p className="text-[10px] text-[var(--console-faint)]">連續失敗 {ops.consecutive_fail}</p>
                </ConsoleSnippetList>
              ) : null}
              <ConsoleSnippetList title="刷新間隔">
                <div className="flex flex-wrap gap-1">
                  {[60, 300, 900].map((sec) => (
                    <button
                      key={sec}
                      type="button"
                      className={`rounded px-1.5 py-0.5 text-[10px] ${
                        ops?.refresh_interval_sec === sec
                          ? 'bg-[color-mix(in_srgb,var(--console-blue)_20%,transparent)] console-status-blue'
                          : 'text-[var(--console-sub)]'
                      }`}
                      onClick={() => void updateLlmOpsPrefs(sec).then(setData)}
                    >
                      {sec >= 60 ? `${sec / 60} 分` : `${sec}s`}
                    </button>
                  ))}
                </div>
              </ConsoleSnippetList>
            </div>
          </ConsoleColumnScroll>
        </ConsoleRightRail>
      </ConsoleThreeColumn>
    </PanelShell>
  );
}
