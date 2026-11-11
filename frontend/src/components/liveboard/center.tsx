/**
 * LiveBoard 中央主區：KPI、狀態堆疊、熱力圖、任務矩陣與各卡片。
 */
import { useMemo } from 'react';
import type { AnimLiveFeed } from '../../lib/animLive';
import type { LabSubTab } from '../../lib/labTabs';
import { buildActivityHeatmap, buildStatusStack, buildTaskDistributionMatrix } from '../../lib/monitorData';
import { useMonitorStore } from '../../stores/monitorStore';
import type { MonitorTab } from '../AppShell';
import {
  ActivityHeatmap,
  MonitorPanel,
  MonitorWarnBar,
  StackBar,
  TaskDistributionMatrix,
} from '../ui/monitor';
import { ApiPoolCard, BudgetCard, CompanyCard, EventsCard, SystemMetricsCard } from './cards';
import { ExternalIntegrationsCard, LabToolsCard } from './integrations';
import { OverviewKpiRow } from './kpis';
import { TaskStackPanel } from './rails';

export function CenterMain({
  feed,
  consoleFeed,
  taskMatrix,
  statusStack,
  capacityFull,
  cacheWarnText,
  dock,
  liteShell,
  onOpenTab,
  onOpenTraces,
  onOpenAgent,
  onOpenLab,
  showTaskStack,
}: {
  feed: AnimLiveFeed;
  consoleFeed: AnimLiveFeed;
  taskMatrix: ReturnType<typeof buildTaskDistributionMatrix>;
  statusStack: ReturnType<typeof buildStatusStack>;
  capacityFull: boolean;
  cacheWarnText?: string;
  dock?: boolean;
  liteShell?: boolean;
  onOpenTab?: (tab: MonitorTab) => void;
  onOpenTraces?: () => void;
  onOpenAgent?: (id: string) => void;
  onOpenLab?: (sub: LabSubTab) => void;
  showTaskStack?: boolean;
}) {
  const dashboard = useMonitorStore((s) => s.dashboard);
  const tasks = dashboard?.tasks ?? [];
  const heatmap = useMemo(() => buildActivityHeatmap(tasks), [tasks]);
  const heatmapEmpty = heatmap.every((r) => r.every((c) => c.level === 0 && !c.error));

  return (
    <div className="mon-live-stack">
      {capacityFull && cacheWarnText ? <MonitorWarnBar>{cacheWarnText}</MonitorWarnBar> : null}
      {!dock && !liteShell && <OverviewKpiRow feed={consoleFeed} />}
      {!dock && !liteShell && statusStack.length > 0 ? (
        <div className="mon-stack-section">
          <p className="mon-stack-section__label">任務狀態比例</p>
          <StackBar segments={statusStack} />
        </div>
      ) : null}
      {showTaskStack ? (
        <TaskStackPanel tasks={tasks} statusStack={statusStack} onOpenTab={onOpenTab} />
      ) : null}
      {!dock && !liteShell ? (
        <MonitorPanel title="活動熱力圖 · 7×24">
          <ActivityHeatmap rows={heatmap} demo={heatmapEmpty} />
        </MonitorPanel>
      ) : null}
      {dock ? (
        <div className="mon-dock-grid">
          <ApiPoolCard feed={feed} onOpen={() => onOpenTab?.('llm')} />
          <CompanyCard
            feed={consoleFeed}
            dock
            onOpen={() => onOpenTab?.('agents')}
            onOpenAgent={onOpenAgent}
            onOpenTab={onOpenTab}
          />
          <BudgetCard feed={feed} dock onOpen={() => onOpenTab?.('models')} />
          <SystemMetricsCard feed={feed} onOpen={() => onOpenTab?.('metrics')} />
          <div className="mon-span-2">
            <EventsCard feed={consoleFeed} dock onOpen={onOpenTraces} />
          </div>
          <div className="mon-span-2">
            <ExternalIntegrationsCard dock onOpenTab={onOpenTab} />
          </div>
          <div className="mon-span-2">
            <LabToolsCard dock onOpenLab={onOpenLab} />
          </div>
        </div>
      ) : (
        <>
          {!liteShell ? (
            <MonitorPanel title="任務分佈矩陣">
              <TaskDistributionMatrix matrix={taskMatrix} demo={taskMatrix.every((r) => r.every((c) => c.count === 0))} />
            </MonitorPanel>
          ) : null}
          <div className="grid gap-2 lg:grid-cols-2">
            <ApiPoolCard feed={feed} onOpen={() => onOpenTab?.('llm')} />
            <CompanyCard
              feed={consoleFeed}
              onOpen={() => onOpenTab?.('agents')}
              onOpenAgent={onOpenAgent}
              onOpenTab={onOpenTab}
            />
          </div>
          <div className="grid gap-2 lg:grid-cols-2">
            <BudgetCard feed={feed} onOpen={() => onOpenTab?.('models')} />
            <SystemMetricsCard feed={feed} onOpen={() => onOpenTab?.('metrics')} />
          </div>
          <EventsCard feed={consoleFeed} onOpen={onOpenTraces} />
          <ExternalIntegrationsCard onOpenTab={onOpenTab} />
          <LabToolsCard onOpenLab={onOpenLab} />
        </>
      )}
    </div>
  );
}
