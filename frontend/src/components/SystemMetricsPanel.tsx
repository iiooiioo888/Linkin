/**
 * SystemMetricsPanel — 系統指標監控（非工業 OPC）。
 *
 * 彙總反思閉環、快取、路由、Trace、任務運行時等 EvoLoop 自身指標。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchOptimizationMonitor } from '../api/client';
import { navPathForTab } from '../lib/monitorTabs';
import type { OptimizationMonitorData } from '../types';
import { RoadmapTable } from './ChatMonitorCards';
import {
  ConsoleCard,
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

type MetricRow = {
  name: string;
  desc: string;
  value: string;
  unit: string;
  pct: number | null;
  status: 'good' | 'warn' | 'idle' | 'info';
  statusLabel: string;
};

function statusClass(status: MetricRow['status']): string {
  switch (status) {
    case 'good':
      return 'console-status-green bg-[color-mix(in_srgb,var(--console-green)_15%,transparent)] px-1.5 py-0.5 rounded';
    case 'warn':
      return 'console-status-amber bg-[color-mix(in_srgb,var(--console-amber)_15%,transparent)] px-1.5 py-0.5 rounded';
    case 'info':
      return 'console-status-blue bg-[color-mix(in_srgb,var(--console-blue)_15%,transparent)] px-1.5 py-0.5 rounded';
    default:
      return 'bg-[var(--console-card)] text-[var(--console-faint)] px-1.5 py-0.5 rounded';
  }
}

function Gauge({ value, min, max }: { value: number | null; min: number; max: number }) {
  const span = max - min || 1;
  const pct = value == null ? 0 : Math.min(100, Math.max(0, ((value - min) / span) * 100));
  const hot = pct >= 85;
  return (
    <div className="h-1.5 w-24 overflow-hidden rounded-full bg-[var(--console-card)]">
      <div
        className="h-full rounded-full"
        style={{
          width: `${pct}%`,
          background: hot ? 'var(--console-danger)' : 'var(--console-blue)',
        }}
      />
    </div>
  );
}

function buildMetricRows(data: OptimizationMonitorData | null): MetricRow[] {
  if (!data) return [];
  const cache = data.llm_cache;
  const hitPct = Math.round((cache?.hit_rate ?? 0) * 100);
  const routing = data.routing_feedback;
  const reflection = data.reflection;
  const userFb = data.user_feedback;
  const trace = data.trace;
  const sys = data.system_stats;
  const edge = data.edge_cache ?? data.opc_edge;
  const reflectionTrace = data.reflection_trace;
  const satisfaction = Math.round((userFb?.satisfaction_rate ?? 0) * 100);

  return [
    {
      name: 'LLM 快取命中率',
      desc: '分層快取（精確 + 語義）',
      value: String(hitPct),
      unit: '%',
      pct: hitPct,
      status: hitPct >= 30 ? 'good' : hitPct > 0 ? 'info' : 'idle',
      statusLabel: hitPct >= 30 ? '良好' : hitPct > 0 ? '累積中' : '待命中',
    },
    {
      name: '反思通過門檻',
      desc: '動態閾值（依任務複雜度調整）',
      value: String(reflection.pass_threshold ?? 8),
      unit: '分',
      pct: ((reflection.pass_threshold ?? 8) / 10) * 100,
      status: 'info',
      statusLabel: '動態',
    },
    {
      name: '路由自適應門檻',
      desc: 'simple / company 字數分界',
      value: String(routing?.adaptive_length_threshold ?? '—'),
      unit: '字',
      pct: null,
      status: (routing?.total ?? 0) >= 10 ? 'good' : 'idle',
      statusLabel: (routing?.total ?? 0) >= 10 ? '學習中' : '樣本不足',
    },
    {
      name: '用戶滿意度',
      desc: '顯式反饋閉環',
      value: String(satisfaction),
      unit: '%',
      pct: satisfaction,
      status: satisfaction >= 70 ? 'good' : satisfaction > 0 ? 'warn' : 'idle',
      statusLabel: satisfaction >= 70 ? '良好' : satisfaction > 0 ? '待改善' : '無樣本',
    },
    {
      name: '任務成功率',
      desc: '運行時任務完成率',
      value: String(sys?.success_rate ?? 0),
      unit: '%',
      pct: sys?.success_rate ?? 0,
      status: (sys?.success_rate ?? 0) >= 80 ? 'good' : (sys?.success_rate ?? 0) > 0 ? 'warn' : 'idle',
      statusLabel: `${sys?.tasks_completed ?? 0}/${sys?.tasks_total ?? 0}`,
    },
    {
      name: '全鏈路 Trace',
      desc: '節點事件軌跡筆數',
      value: String(trace?.trace_count ?? 0),
      unit: '筆',
      pct: null,
      status: (trace?.trace_count ?? 0) > 0 ? 'good' : 'idle',
      statusLabel: (trace?.trace_count ?? 0) > 0 ? '記錄中' : '尚無',
    },
    {
      name: '分層快取',
      desc: 'LLM 精確 + 語義快取',
      value: String(edge?.entry_count ?? 0),
      unit: `/${edge?.max_size ?? 512}`,
      pct: edge?.max_size ? ((edge?.entry_count ?? 0) / edge.max_size) * 100 : null,
      status: (edge?.hit_rate ?? 0) >= 0.3 ? 'good' : (edge?.entry_count ?? 0) > 0 ? 'info' : 'idle',
      statusLabel: `命中 ${Math.round((edge?.hit_rate ?? 0) * 100)}%`,
    },
    {
      name: '反思迭代上限',
      desc: '早停 + 最大輪次',
      value: String(reflection.max_iterations ?? 3),
      unit: '輪',
      pct: null,
      status: 'info',
      statusLabel: `Δ${reflection.min_score_improvement ?? 0.5}`,
    },
    {
      name: '反思鏈路均耗時',
      desc: 'evaluate + reflect + improve（Trace 彙總）',
      value:
        reflectionTrace?.avg_loop_duration_ms != null
          ? String(Math.round(reflectionTrace.avg_loop_duration_ms))
          : '—',
      unit: reflectionTrace?.avg_loop_duration_ms != null ? 'ms' : '',
      pct: null,
      status: (reflectionTrace?.tasks_analyzed ?? 0) > 0 ? 'info' : 'idle',
      statusLabel:
        reflectionTrace?.tasks_analyzed != null && reflectionTrace.tasks_analyzed > 0
          ? `${reflectionTrace.tasks_analyzed} 任務`
          : '尚無軌跡',
    },
    {
      name: '反思改進幅度',
      desc: '首輪與末輪評分差（Trace 彙總）',
      value:
        reflectionTrace?.avg_score_delta != null
          ? String(reflectionTrace.avg_score_delta)
          : '—',
      unit: reflectionTrace?.avg_score_delta != null ? '分' : '',
      pct: null,
      status:
        (reflectionTrace?.avg_score_delta ?? 0) >= 0.5
          ? 'good'
          : (reflectionTrace?.tasks_analyzed ?? 0) > 0
            ? 'warn'
            : 'idle',
      statusLabel:
        reflectionTrace?.improvement_rate_pct != null
          ? `提升率 ${reflectionTrace.improvement_rate_pct}%`
          : '—',
    },
  ];
}

export default function SystemMetricsPanel() {
  const [data, setData] = useState<OptimizationMonitorData | null>(null);
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
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 6000);
    return () => clearInterval(timer);
  }, [refresh]);

  const rows = useMemo(() => buildMetricRows(data), [data]);
  const cache = data?.llm_cache;
  const hitPct = Math.round((cache?.hit_rate ?? 0) * 100);
  const sys = data?.system_stats;
  const reflectionTrace = data?.reflection_trace;
  const activeCount = data?.roadmap?.filter((r) => r.status === 'active').length ?? 0;

  return (
    <PanelShell scroll={false}>
      <ConsoleThreeColumn>
        <ConsoleLeftRail>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-4">
            <h1 className="text-[15px] font-semibold text-[var(--console-ink)]">運行指標</h1>
            <p className="mt-1 text-[10px] text-[var(--console-faint)]">快取 · 反思 · Trace</p>
          </div>
          <ConsoleColumnScroll className="!px-0 !py-0">
            <ConsoleRailNav
              sections={[
                { id: 'metrics-main', label: '指標總覽' },
                { id: 'metrics-roadmap', label: '優化路線' },
                { id: 'metrics-reflection', label: '反思鏈路' },
              ]}
              activeId="metrics-main"
              onSelect={() => {}}
            />
          </ConsoleColumnScroll>
        </ConsoleLeftRail>

        <ConsoleCenterColumn>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-3">
            <SectionHeader
              title="運行指標"
              description="快取 · 反思 · 優化路線圖 · 環節模型（非工業 OPC）"
              meta={
                <>
                  API 金鑰在{' '}
                  <a href="#/monitor/llm" className="console-status-blue hover:underline">
                    {navPathForTab('llm')}
                  </a>
                  ；用量在{' '}
                  <a href="#/monitor/models" className="console-status-blue hover:underline">
                    計費 → AI 用量
                  </a>
                  。
                </>
              }
              actions={
                <>
                  <span className="rounded-full bg-[color-mix(in_srgb,var(--console-green)_15%,transparent)] px-2.5 py-0.5 text-[11px] console-status-green">
                    {activeCount} 項優化啟用
                  </span>
                  <button type="button" onClick={() => void refresh()} className={consoleLayout.refreshBtn}>
                    {loading ? '同步中' : '重新整理'}
                  </button>
                </>
              }
            />
          </div>
          <ConsoleColumnScroll>
            {error ? <PanelAlert className="mb-3">{error}</PanelAlert> : null}

            <KpiGrid>
              {[
                { label: '快取命中', value: `${hitPct}%` },
                { label: '任務成功率', value: `${sys?.success_rate ?? 0}%` },
                {
                  label: '反思均輪次',
                  value: reflectionTrace?.avg_iterations != null ? String(reflectionTrace.avg_iterations) : '—',
                },
                { label: 'Trace', value: String(data?.trace.trace_count ?? 0) },
              ].map((kpi) => (
                <KpiCard key={kpi.label} label={kpi.label} value={kpi.value} />
              ))}
            </KpiGrid>

            <ConsoleCard className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[640px] text-left">
                <thead>
                  <tr className="border-b border-[var(--console-line)] text-[10px] uppercase tracking-wider text-[var(--console-faint)]">
                    <th className="px-3 py-2 font-medium">指標</th>
                    <th className="px-3 py-2 font-medium">即時值</th>
                    <th className="px-3 py-2 font-medium">趨勢</th>
                    <th className="px-3 py-2 font-medium">狀態</th>
                  </tr>
                </thead>
                <tbody className="px-3">
                  {rows.map((row) => (
                    <tr key={row.name} className="border-b border-[var(--console-line)] last:border-0">
                      <td className="py-2 pr-3">
                        <p className="text-xs font-medium text-[var(--console-ink)]">{row.name}</p>
                        <p className="text-[10px] text-[var(--console-faint)]">{row.desc}</p>
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs tabular-nums text-[var(--console-sub)]">
                        {row.value}
                        {row.unit ? <span className="ml-1 text-[var(--console-faint)]">{row.unit}</span> : null}
                      </td>
                      <td className="py-2 pr-3">
                        {row.pct != null ? (
                          <>
                            <Gauge value={row.pct} min={0} max={100} />
                            <p className="mt-0.5 text-[10px] text-[var(--console-faint)]">0–100</p>
                          </>
                        ) : (
                          <span className="text-[10px] text-[var(--console-faint)]">—</span>
                        )}
                      </td>
                      <td className="py-2">
                        <span className={`text-[10px] ${statusClass(row.status)}`}>{row.statusLabel}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ConsoleCard>

            <div className="mt-3">
              <RoadmapTable items={data?.roadmap ?? []} />
            </div>

            <ConsoleCard className="mt-3">
              <ConsoleCardHeader>反思鏈路追蹤（輪次 · 耗時 · 改進幅度）</ConsoleCardHeader>
              <table className="w-full text-left text-[12px]">
                <thead className="bg-[var(--console-card)] text-[10px] uppercase tracking-wider text-[var(--console-faint)]">
                  <tr>
                    <th className="px-3 py-2 font-medium">任務</th>
                    <th className="px-3 py-2 font-medium">輪次</th>
                    <th className="px-3 py-2 font-medium">分數</th>
                    <th className="px-3 py-2 font-medium">Δ</th>
                    <th className="px-3 py-2 font-medium">反思耗時</th>
                    <th className="px-3 py-2 font-medium">狀態</th>
                  </tr>
                </thead>
                <tbody>
                  {(reflectionTrace?.recent_cycles ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-3 py-3 text-xs text-[var(--console-faint)]">
                        尚無反思軌跡，完成任務後將自動彙總。
                      </td>
                    </tr>
                  ) : (
                    reflectionTrace?.recent_cycles.map((cycle) => (
                      <tr key={cycle.task_id} className="border-t border-[var(--console-line)]">
                        <td className="px-3 py-1.5 font-mono text-[10px] text-[var(--console-sub)]">
                          {cycle.task_id.slice(0, 12)}
                          {cycle.task_id.length > 12 ? '…' : ''}
                        </td>
                        <td className="px-3 py-1.5 tabular-nums text-[var(--console-sub)]">{cycle.iterations}</td>
                        <td className="px-3 py-1.5 tabular-nums text-[var(--console-sub)]">
                          {cycle.score_start != null && cycle.score_end != null
                            ? `${cycle.score_start} → ${cycle.score_end}`
                            : '—'}
                        </td>
                        <td className="px-3 py-1.5 tabular-nums console-status-blue">
                          {cycle.score_delta != null ? `+${cycle.score_delta}` : '—'}
                        </td>
                        <td className="px-3 py-1.5 tabular-nums text-[var(--console-sub)]">
                          {cycle.loop_duration_ms > 0 ? `${Math.round(cycle.loop_duration_ms)}ms` : '—'}
                        </td>
                        <td className="px-3 py-1.5">
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] ${
                              cycle.early_stop
                                ? 'console-status-amber bg-[color-mix(in_srgb,var(--console-amber)_15%,transparent)]'
                                : 'console-status-green bg-[color-mix(in_srgb,var(--console-green)_15%,transparent)]'
                            }`}
                          >
                            {cycle.early_stop ? '早停' : '完成'}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </ConsoleCard>

            <ConsoleCard className="mt-3">
              <ConsoleCardHeader>環節 → 模型層級（P0 任務-模型匹配）</ConsoleCardHeader>
              <table className="w-full text-left text-[12px]">
                <thead className="bg-[var(--console-card)] text-[10px] uppercase tracking-wider text-[var(--console-faint)]">
                  <tr>
                    <th className="px-3 py-2 font-medium">環節</th>
                    <th className="px-3 py-2 font-medium">Tier</th>
                    <th className="px-3 py-2 font-medium">模型</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data?.stage_router ?? {}).map(([stage, info]) => (
                    <tr key={stage} className="border-t border-[var(--console-line)]">
                      <td className="px-3 py-1.5 font-mono text-[var(--console-sub)]">{stage}</td>
                      <td className="px-3 py-1.5 console-status-blue">{info.tier}</td>
                      <td className="px-3 py-1.5 font-mono text-[var(--console-sub)]">{info.model}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ConsoleCard>
          </ConsoleColumnScroll>
        </ConsoleCenterColumn>

        <ConsoleRightRail>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-3">
            <p className="text-[11px] font-semibold text-[var(--console-ink)]">快照</p>
          </div>
          <ConsoleColumnScroll>
            <div className={consoleLayout.sectionStack}>
              <ConsoleSnippetList title="快取">
                <div className={consoleLayout.snippetRow}>
                  <span>命中率</span>
                  <span className="console-status-green">{hitPct}%</span>
                </div>
                <div className={consoleLayout.snippetRow}>
                  <span>命中 / 未命中</span>
                  <span className="text-[var(--console-sub)]">
                    {cache?.hits ?? 0} / {cache?.misses ?? 0}
                  </span>
                </div>
              </ConsoleSnippetList>
              <ConsoleSnippetList title="任務">
                <div className={consoleLayout.snippetRow}>
                  <span>成功率</span>
                  <span className="console-status-green">{sys?.success_rate ?? 0}%</span>
                </div>
                <div className={consoleLayout.snippetRow}>
                  <span>完成 / 總計</span>
                  <span className="text-[var(--console-sub)]">
                    {sys?.tasks_completed ?? 0} / {sys?.tasks_total ?? 0}
                  </span>
                </div>
              </ConsoleSnippetList>
              <ConsoleSnippetList title="優化">
                <div className={consoleLayout.snippetRow}>
                  <span>啟用中</span>
                  <span className="console-status-accent">{activeCount}</span>
                </div>
              </ConsoleSnippetList>
            </div>
          </ConsoleColumnScroll>
        </ConsoleRightRail>
      </ConsoleThreeColumn>
    </PanelShell>
  );
}
