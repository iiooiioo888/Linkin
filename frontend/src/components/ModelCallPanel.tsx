/**
 * ModelCallPanel — 模型調用分布（從 Trace llm_call 事件彙總）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchLlmOps, fetchOptimizationMonitor } from '../api/client';
import { extraRateItems, fmtPerMillion, fmtRate, lookupRateCard } from '../lib/agentUi';
import { navPathForTab } from '../lib/monitorTabs';
import type { ModelRateCatalog, OptimizationMonitorData } from '../types';
import { CHART_PALETTE, consoleColors } from '../lib/consoleColors';
import LcBarChart from './charts/LcBarChart';
import {
  ConsoleCard,
  ConsoleCardBody,
  ConsoleCardHeader,
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  ConsoleLeftRail,
  ConsoleRailNav,
  ConsoleRightRail,
  ConsoleSnippetList,
  ConsoleThreeColumn,
  KpiCard,
  KpiGrid,
  PanelAlert,
  PanelShell,
  SectionHeader,
  consoleLayout,
} from './ui/ConsoleLayout';

function Bar({ pct, color = consoleColors.blue }: { pct: number; color?: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--console-card)]">
      <div className="h-full rounded-full transition-all" style={{ width: `${Math.min(100, pct)}%`, background: color }} />
    </div>
  );
}

const PHASE_COLORS = [...CHART_PALETTE];

export default function ModelCallPanel() {
  const [data, setData] = useState<OptimizationMonitorData | null>(null);
  const [rates, setRates] = useState<ModelRateCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchOptimizationMonitor();
      setData(next);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
    try {
      const ops = await fetchLlmOps();
      setRates(ops.model_rate_cards ?? null);
    } catch {
      setRates(null);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 8000);
    return () => clearInterval(timer);
  }, [refresh]);

  const calls = data?.model_calls;
  const topModel = calls?.by_model?.[0];

  const phaseRows = useMemo(
    () => (calls?.by_phase ?? []).map((row, i) => ({ ...row, color: PHASE_COLORS[i % PHASE_COLORS.length] })),
    [calls?.by_phase],
  );

  return (
    <PanelShell scroll={false}>
      <ConsoleThreeColumn>
        <ConsoleLeftRail>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-4">
            <h1 className="text-[15px] font-semibold text-[var(--console-ink)]">調用用量</h1>
            <p className="mt-1 text-[10px] text-[var(--console-faint)]">Trace llm_call 彙總</p>
          </div>
          <ConsoleColumnScroll className="!px-0 !py-0">
            <ConsoleRailNav
              sections={[
                { id: 'models-overview', label: '總覽' },
                { id: 'models-by-model', label: '按模型' },
                { id: 'models-by-phase', label: '按環節' },
              ]}
              activeId="models-overview"
              onSelect={() => {}}
            />
          </ConsoleColumnScroll>
        </ConsoleLeftRail>

        <ConsoleCenterColumn>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-3">
            <SectionHeader
              title="調用用量"
              description="從全鏈路 Trace 彙總 LLM 調用 · 按模型與環節統計"
              meta={
                <>
                  要改金鑰或目錄請到{' '}
                  <a href="#/monitor/llm" className="console-status-blue hover:underline">
                    {navPathForTab('llm')}
                  </a>
                  。
                </>
              }
              actions={
                <button type="button" onClick={() => void refresh()} className={consoleLayout.refreshBtn}>
                  {loading ? '同步中' : '重新整理'}
                </button>
              }
            />
          </div>
          <ConsoleColumnScroll>
            {error ? <PanelAlert className="mb-3">{error}</PanelAlert> : null}

            <KpiGrid>
              {[
                { label: '總調用', value: String(calls?.total_calls ?? 0) },
                { label: '掃描軌跡', value: String(calls?.files_scanned ?? 0) },
                { label: '平均耗時', value: calls?.avg_duration_ms != null ? `${calls.avg_duration_ms}ms` : '—' },
                { label: '主力模型', value: topModel?.model?.split('/').pop() ?? '—' },
              ].map((kpi) => (
                <KpiCard key={kpi.label} label={kpi.label} value={kpi.value} valueClassName="truncate text-sm" />
              ))}
            </KpiGrid>

            <ConsoleCard className="mt-3">
              <ConsoleCardHeader>模型佔比</ConsoleCardHeader>
              <div className={`h-[220px] ${consoleLayout.cardBody}`}>
                {(calls?.by_model ?? []).length === 0 ? (
                  <p className="p-3 text-xs text-[var(--console-faint)]">尚無 llm_call 軌跡，完成任務後將自動彙總。</p>
                ) : (
                  <LcBarChart
                    height={200}
                    categories={(calls?.by_model ?? []).slice(0, 8).map((row) => row.model.split('/').pop() ?? row.model)}
                    groups={[
                      {
                        subCategory: '調用次數',
                        values: (calls?.by_model ?? []).slice(0, 8).map((row) => row.count),
                      },
                    ]}
                  />
                )}
              </div>
            </ConsoleCard>

            <div className={`mt-3 ${consoleLayout.cardGrid}`}>
              <ConsoleCard>
                <ConsoleCardHeader>按模型</ConsoleCardHeader>
                <ConsoleCardBody dense className="max-h-[360px] space-y-3 overflow-y-auto">
                  {(calls?.by_model ?? []).length === 0 ? (
                    <p className="text-xs text-[var(--console-faint)]">尚無 llm_call 軌跡，完成任務後將自動彙總。</p>
                  ) : (
                    calls?.by_model.map((row) => (
                      <div key={row.model}>
                        <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                          <span className="truncate font-mono text-[var(--console-sub)]">{row.model}</span>
                          <span className="shrink-0 tabular-nums text-[var(--console-sub)]">
                            {row.count} · {row.share_pct}%
                          </span>
                        </div>
                        <Bar pct={row.share_pct} />
                        <p className="mt-0.5 text-[10px] text-[var(--console-faint)]">
                          {row.avg_duration_ms != null ? `均 ${row.avg_duration_ms}ms` : '—'}
                          {row.cost > 0 ? ` · $${row.cost.toFixed(4)}` : ''}
                        </p>
                      </div>
                    ))
                  )}
                </ConsoleCardBody>
              </ConsoleCard>

              <ConsoleCard>
                <ConsoleCardHeader>按環節（phase）</ConsoleCardHeader>
                <ConsoleCardBody dense className="max-h-[360px] space-y-3 overflow-y-auto">
                  {phaseRows.length === 0 ? (
                    <p className="text-xs text-[var(--console-faint)]">—</p>
                  ) : (
                    phaseRows.map((row) => (
                      <div key={row.phase}>
                        <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                          <span className="font-mono text-[var(--console-sub)]">{row.phase}</span>
                          <span className="tabular-nums text-[var(--console-sub)]">
                            {row.count} · {row.share_pct}%
                          </span>
                        </div>
                        <Bar pct={row.share_pct} color={row.color} />
                      </div>
                    ))
                  )}
                </ConsoleCardBody>
              </ConsoleCard>
            </div>

            <ConsoleCard className="mt-3">
              <ConsoleCardHeader>
                公開價目 · {rates?.models?.length ?? 0} 模型 · {rates?.fields?.length ?? 0} 收費項
              </ConsoleCardHeader>
              <ConsoleCardBody dense className="max-h-[420px] space-y-3 overflow-y-auto">
                {(rates?.models ?? []).length === 0 ? (
                  <p className="text-xs text-[var(--console-faint)]">尚無價目。請到 API 路由檢查目錄。</p>
                ) : (
                  (rates?.models ?? []).map((row) => {
                    const extras = extraRateItems(lookupRateCard(row.id, rates));
                    return (
                      <div key={row.id}>
                        <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                          <span className="truncate font-mono text-[var(--console-sub)]">{row.id}</span>
                          <span className="shrink-0 tabular-nums text-[var(--console-sub)]">
                            輸入 {fmtPerMillion(row.input)} · 輸出 {fmtPerMillion(row.output)}
                          </span>
                        </div>
                        {extras.length ? (
                          <div className="flex flex-wrap gap-1">
                            {extras.map((item) => (
                              <span
                                key={item.id}
                                className="rounded bg-[color-mix(in_srgb,var(--console-ink)_4%,transparent)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--console-sub)]"
                              >
                                {item.label} {fmtRate(item.usd_per_1m, item.unit)}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <p className="text-[10px] text-[var(--console-faint)]">僅輸入／輸出</p>
                        )}
                      </div>
                    );
                  })
                )}
              </ConsoleCardBody>
            </ConsoleCard>
          </ConsoleColumnScroll>
        </ConsoleCenterColumn>

        <ConsoleRightRail>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-3">
            <p className="text-[11px] font-semibold text-[var(--console-ink)]">主力模型</p>
          </div>
          <ConsoleColumnScroll>
            <div className={consoleLayout.sectionStack}>
              <ConsoleSnippetList title="Top 模型">
                {(calls?.by_model ?? []).slice(0, 5).map((row) => (
                  <div key={row.model} className={consoleLayout.snippetRow}>
                    <span className="truncate font-mono">{row.model.split('/').pop() ?? row.model}</span>
                    <span className="console-status-blue">{row.share_pct}%</span>
                  </div>
                ))}
              </ConsoleSnippetList>
            </div>
          </ConsoleColumnScroll>
        </ConsoleRightRail>
      </ConsoleThreeColumn>
    </PanelShell>
  );
}
