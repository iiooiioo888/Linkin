/**
 * ModelCallPanel — 模型調用分布（從 Trace llm_call 事件彙總）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchLlmOps, fetchOptimizationMonitor } from '../api/client';
import { extraRateItems, fmtPerMillion, fmtRate, lookupRateCard } from '../lib/agentUi';
import { navPathForTab } from '../lib/monitorTabs';
import type { ModelRateCatalog, OptimizationMonitorData } from '../types';
import LcBarChart from './charts/LcBarChart';

function Bar({ pct, color = '#007AFF' }: { pct: number; color?: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#141516]">
      <div className="h-full rounded-full transition-all" style={{ width: `${Math.min(100, pct)}%`, background: color }} />
    </div>
  );
}

const PHASE_COLORS = ['#007AFF', '#64D2FF', '#4cc38a', '#f5a524', '#e5484d', '#a78bfa'];

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
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto apple-canvas p-4 text-[#f7f8f8]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">調用用量</h2>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">
            從全鏈路 Trace 彙總 LLM 調用 · 按模型與環節統計
          </p>
          <p className="mt-1 text-[11px] text-[#636366]">
            要改金鑰或目錄請到{' '}
            <a href="#/monitor/llm" className="text-[#64D2FF] hover:underline">
              {navPathForTab('llm')}
            </a>
            。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8]"
        >
          {loading ? '同步中' : '重新整理'}
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
        {[
          { label: '總調用', value: String(calls?.total_calls ?? 0) },
          { label: '掃描軌跡', value: String(calls?.files_scanned ?? 0) },
          { label: '平均耗時', value: calls?.avg_duration_ms != null ? `${calls.avg_duration_ms}ms` : '—' },
          { label: '主力模型', value: topModel?.model?.split('/').pop() ?? '—' },
        ].map((kpi) => (
          <div key={kpi.label} className="apple-card apple-card--tight !p-0 px-3 py-2.5">
            <p className="text-[10px] uppercase tracking-wider text-[#62666d]">{kpi.label}</p>
            <p className="mt-1 truncate font-mono text-sm text-[#f7f8f8]">{kpi.value}</p>
          </div>
        ))}
      </div>

      <div className="mb-4 apple-card apple-card--tight !p-0 overflow-hidden">
        <p className="border-b border-white/[0.08] bg-[#1C1C1E] px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[#62666d]">
          模型佔比
        </p>
        <div className="h-[220px] p-2">
          {(calls?.by_model ?? []).length === 0 ? (
            <p className="p-3 text-xs text-[#62666d]">尚無 llm_call 軌跡，完成任務後將自動彙總。</p>
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
      </div>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
        <div className="apple-card apple-card--tight !p-0 overflow-hidden">
          <p className="border-b border-white/[0.08] bg-[#1C1C1E] px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[#62666d]">
            按模型
          </p>
          <div className="max-h-[360px] overflow-y-auto p-3 space-y-3">
            {(calls?.by_model ?? []).length === 0 ? (
              <p className="text-xs text-[#62666d]">尚無 llm_call 軌跡，完成任務後將自動彙總。</p>
            ) : (
              calls?.by_model.map((row) => (
                <div key={row.model}>
                  <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                    <span className="truncate font-mono text-[#d0d6e0]">{row.model}</span>
                    <span className="shrink-0 tabular-nums text-[#8a8f98]">
                      {row.count} · {row.share_pct}%
                    </span>
                  </div>
                  <Bar pct={row.share_pct} />
                  <p className="mt-0.5 text-[10px] text-[#62666d]">
                    {row.avg_duration_ms != null ? `均 ${row.avg_duration_ms}ms` : '—'}
                    {row.cost > 0 ? ` · $${row.cost.toFixed(4)}` : ''}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="apple-card apple-card--tight !p-0 overflow-hidden">
          <p className="border-b border-white/[0.08] bg-[#1C1C1E] px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[#62666d]">
            按環節（phase）
          </p>
          <div className="max-h-[360px] overflow-y-auto p-3 space-y-3">
            {phaseRows.length === 0 ? (
              <p className="text-xs text-[#62666d]">—</p>
            ) : (
              phaseRows.map((row) => (
                <div key={row.phase}>
                  <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                    <span className="font-mono text-[#d0d6e0]">{row.phase}</span>
                    <span className="tabular-nums text-[#8a8f98]">
                      {row.count} · {row.share_pct}%
                    </span>
                  </div>
                  <Bar pct={row.share_pct} color={row.color} />
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="mt-4 apple-card apple-card--tight !p-0 overflow-hidden">
        <p className="border-b border-white/[0.08] bg-[#1C1C1E] px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[#62666d]">
          公開價目 · {rates?.models?.length ?? 0} 模型 · {rates?.fields?.length ?? 0} 收費項
        </p>
        <div className="max-h-[420px] overflow-y-auto p-3 space-y-3">
          {(rates?.models ?? []).length === 0 ? (
            <p className="text-xs text-[#62666d]">尚無價目。請到 API 路由檢查目錄。</p>
          ) : (
            (rates?.models ?? []).map((row) => {
              const extras = extraRateItems(lookupRateCard(row.id, rates));
              return (
                <div key={row.id}>
                  <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                    <span className="truncate font-mono text-[#d0d6e0]">{row.id}</span>
                    <span className="shrink-0 tabular-nums text-[#8a8f98]">
                      輸入 {fmtPerMillion(row.input)} · 輸出 {fmtPerMillion(row.output)}
                    </span>
                  </div>
                  {extras.length ? (
                    <div className="flex flex-wrap gap-1">
                      {extras.map((item) => (
                        <span
                          key={item.id}
                          className="rounded bg-white/[0.04] px-1.5 py-0.5 font-mono text-[10px] text-[#AEAEB2]"
                        >
                          {item.label} {fmtRate(item.usd_per_1m, item.unit)}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[10px] text-[#62666d]">僅輸入／輸出</p>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
