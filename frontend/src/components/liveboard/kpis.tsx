/**
 * LiveBoard 首屏 KPI 列。
 */
import type { AnimLiveFeed } from '../../lib/animLive';
import { buildSparkSeries24 } from '../../lib/monitorData';
import { useMonitorStore } from '../../stores/monitorStore';
import { KpiSparkCard, MonitorKpiGrid } from '../ui/monitor';

export function OverviewKpiRow({ feed }: { feed: AnimLiveFeed }) {
  const dashboard = useMonitorStore((s) => s.dashboard);
  const tasks = dashboard?.tasks ?? [];
  const opt = feed.optimization;
  const hitPct = Math.round((opt?.llm_cache.hit_rate ?? 0) * 100);
  const successRate = opt?.system_stats?.success_rate ?? 0;
  const spark = buildSparkSeries24(opt ?? null, tasks);

  return (
    <MonitorKpiGrid>
      {[
        { label: '快取命中', value: `${hitPct}%`, accent: true },
        { label: '成功率', value: `${successRate}%` },
        { label: '執行中', value: String(feed.runningTasks) },
        { label: '席位', value: String(feed.agents.length) },
        { label: 'Trace', value: String(opt?.trace.trace_count ?? 0) },
        { label: 'API', value: String(feed.llmOps?.api_routes?.length ?? 0) },
      ].map((kpi) => (
        <KpiSparkCard
          key={kpi.label}
          label={kpi.label}
          value={kpi.value}
          spark={spark}
          accent={kpi.accent}
          size="lg"
        />
      ))}
    </MonitorKpiGrid>
  );
}
