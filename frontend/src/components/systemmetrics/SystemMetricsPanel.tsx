/**
 * SystemMetricsPanel — 系統總覽（OCD 三欄 · 非工業 OPC）。
 *
 * 彙總反思閉環、快取、路由、Trace、任務運行時等 Linkin 自身指標。
 *
 * 第十輪重構：表格／右欄子元件與指標建構函式已拆至 ./systemmetrics/；
 * 本檔保留全部 hooks 與三欄骨架（hooks 呼叫順序與資料流不變）。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchOptimizationMonitor } from '../../api/client';
import { navPathForTab } from '../../lib/monitorTabs';
import type { OptimizationMonitorData } from '../../types';
import { RoadmapTable } from '../ChatMonitorCards';
import {
  buildActivityHeatmap,
  buildSparkSeries24,
  buildStatusStack,
  hostResourceGauges,
} from '../../lib/monitorData';
import { useHostResources } from '../../lib/hostResources';
import {
  ActivityHeatmap,
  KpiSparkCard,
  ResourceGauges,
  StackBar,
} from '../ui/monitor';
import {
  ConsoleCard,
  ConsoleCardHeader,
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  ConsoleLeftRail,
  ConsoleRailNav,
  ConsoleThreeColumn,
  KpiGrid6,
  PanelAlert,
  PanelShell,
  SectionHeader,
  WarnBar,
  consoleLayout,
} from '../ui/ConsoleLayout';
import { formatPercentKpiParts, normalizePercentNumber } from '../../lib/formatMetrics';
import { useMonitorStore } from '../../stores/monitorStore';
import { MetricTable } from './MetricTable';
import { ReflectionCyclesCard } from './ReflectionCyclesCard';
import { RightRail } from './RightRail';
import { StageRouterCard } from './StageRouterCard';
import { buildMetricRows } from './metrics';

export default function SystemMetricsPanel() {
  const dashboard = useMonitorStore((s) => s.dashboard);
  const [data, setData] = useState<OptimizationMonitorData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const hostGauges = hostResourceGauges(useHostResources());

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
  const taskSuccessPct = normalizePercentNumber(sys?.success_rate);
  const reflectionTrace = data?.reflection_trace;
  const activeCount = data?.roadmap?.filter((r) => r.status === 'active').length ?? 0;
  const recentCycles = reflectionTrace?.recent_cycles ?? [];
  const systemHealthy = (sys?.success_rate ?? 0) >= 70 && hitPct >= 20;
  const tasks = dashboard?.tasks ?? [];
  const heatmap = buildActivityHeatmap(tasks);
  const heatmapEmpty = heatmap.every((r) => r.every((c) => c.level === 0 && !c.error));
  const spark = buildSparkSeries24(data, tasks);
  const statusStack = buildStatusStack(sys ?? {});
  const edge = data?.edge_cache ?? data?.opc_edge;
  const cacheCapPct = edge?.max_size ? ((edge.entry_count ?? 0) / edge.max_size) * 100 : 0;
  const capacityFull = cacheCapPct >= 100;

  const quickActions = [
    { label: 'API 路由', href: '#/monitor/llm' },
    { label: '任務隊列', href: '#/monitor/tasks' },
    { label: 'AI 用量', href: '#/monitor/models' },
    { label: '基礎設施', href: '#/monitor/ops' },
  ];

  return (
    <PanelShell scroll={false}>
      <ConsoleThreeColumn>
        <ConsoleLeftRail>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-4">
            <h1 className="text-[15px] font-semibold text-[var(--console-ink)]">系統總覽</h1>
            <p className="mt-1 text-[10px] text-[var(--console-faint)]">Linkin 運行時</p>
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
              title="系統總覽"
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
            {capacityFull ? (
              <WarnBar className="mb-3">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--console-amber)]" />
                快取容量已達 100%（{edge?.entry_count ?? 0}/{edge?.max_size ?? 512}）— 建議清理或調高上限
              </WarnBar>
            ) : null}

            <KpiGrid6>
              {[
                { label: '快取命中', value: `${hitPct}%`, accent: true },
                {
                  label: '任務成功率',
                  ...formatPercentKpiParts(taskSuccessPct ?? 0),
                },
                {
                  label: '反思均輪次',
                  value: reflectionTrace?.avg_iterations != null ? String(reflectionTrace.avg_iterations) : '—',
                },
                { label: 'Trace', value: String(data?.trace.trace_count ?? 0) },
                { label: '執行中', value: String(sys?.tasks_running ?? 0) },
                { label: '迭代總計', value: String(sys?.total_iterations ?? 0) },
              ].map((kpi) => (
                <KpiSparkCard
                  key={kpi.label}
                  label={kpi.label}
                  value={kpi.value}
                  unit={'unit' in kpi ? kpi.unit : undefined}
                  spark={spark}
                  accent={'accent' in kpi ? kpi.accent : undefined}
                />
              ))}
            </KpiGrid6>

            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              <ConsoleCard>
                <ConsoleCardHeader>活動熱力圖</ConsoleCardHeader>
                <div className="p-3">
                  <ActivityHeatmap rows={heatmap} demo={heatmapEmpty} />
                </div>
              </ConsoleCard>
              <ConsoleCard>
                <ConsoleCardHeader>資源概覽</ConsoleCardHeader>
                <div className="p-3">
                  <ResourceGauges gauges={hostGauges} />
                  <p className="mt-2 text-center text-[10px] text-[var(--console-faint)]">主機 CPU／記憶體／網路。不是任務數估算。</p>
                  {statusStack.length > 0 ? (
                    <div className="mt-4">
                      <p className="mb-1.5 text-[9px] font-semibold text-[var(--console-faint)]">任務狀態</p>
                      <StackBar segments={statusStack} />
                    </div>
                  ) : null}
                </div>
              </ConsoleCard>
            </div>
            <MetricTable rows={rows} />

            <div className="mt-3">
              <RoadmapTable items={data?.roadmap ?? []} />
            </div>

            <ReflectionCyclesCard reflectionTrace={reflectionTrace} />

            <StageRouterCard data={data} />

          </ConsoleColumnScroll>
        </ConsoleCenterColumn>
        <RightRail
          systemHealthy={systemHealthy}
          activeCount={activeCount}
          hitPct={hitPct}
          recentCycles={recentCycles}
          quickActions={quickActions}
        />
      </ConsoleThreeColumn>
    </PanelShell>
  );
}
