/**
 * LiveBoard 細節開關、任務狀態堆疊與右欄內容。
 */
import { useMemo, type ReactNode } from 'react';
import type { AnimLiveFeed } from '../../lib/animLive';
import { buildStatusStack, hostResourceGauges, taskPriority } from '../../lib/monitorData';
import { useHostResources } from '../../lib/hostResources';
import { useMonitorStore } from '../../stores/monitorStore';
import type { TaskSummary } from '../../types';
import type { MonitorTab } from '../AppShell';
import { MonitorPanel, ResourceGauges, StackBar, TaskPriorityCard } from '../ui/monitor';
import { ApiPoolCard, CompanyCard } from './cards';

export function LiveBoardDetailsToggle({
  open,
  onToggle,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className="mon-live-details">
      <button
        type="button"
        className="mon-live-details__toggle"
        onClick={onToggle}
        aria-expanded={open}
        data-testid="monitor-live-details-toggle"
      >
        <span>{open ? '收起監控細節' : '展開監控細節'}</span>
        <span className="mon-live-details__chevron" aria-hidden>{open ? '▴' : '▾'}</span>
      </button>
      {open ? <div className="mon-live-details__body">{children}</div> : null}
    </div>
  );
}

export function TaskStackPanel({
  tasks,
  statusStack,
  onOpenTab,
}: {
  tasks: TaskSummary[];
  statusStack: ReturnType<typeof buildStatusStack>;
  onOpenTab?: (tab: MonitorTab) => void;
}) {
  const sorted = useMemo(() => {
    const order = { p1: 0, p2: 1, p3: 2 };
    return [...tasks]
      .sort((a, b) => order[taskPriority(a)] - order[taskPriority(b)])
      .slice(0, 8);
  }, [tasks]);

  return (
    <div className="mon-stack-section">
      <p className="mon-stack-section__label">任務狀態堆疊</p>
      {statusStack.length > 0 ? <StackBar segments={statusStack} /> : null}
      <div className="mon-task-stack mt-3">
        {sorted.length === 0 ? (
          <p className="py-4 text-center text-[11px] text-[var(--console-faint)]">尚無任務</p>
        ) : (
          sorted.map((task) => {
            const shortId = task.task_id.replace(/^.*[#-]/, '').slice(-4) || task.task_id.slice(0, 4);
            return (
              <TaskPriorityCard
                key={task.task_id}
                priority={taskPriority(task)}
                title={task.query || '（無標題）'}
                onClick={() => onOpenTab?.('tasks')}
                meta={
                  <>
                    <span>{task.status}</span>
                    <span>#{shortId}</span>
                  </>
                }
              />
            );
          })
        )}
      </div>
    </div>
  );
}

export function RightRailContent({
  feed,
  consoleFeed,
  statusStack,
  onOpenTab,
  onOpenAgent,
}: {
  feed: AnimLiveFeed;
  consoleFeed: AnimLiveFeed;
  statusStack: ReturnType<typeof buildStatusStack>;
  onOpenTab?: (tab: MonitorTab) => void;
  onOpenAgent?: (id: string) => void;
}) {
  const dashboard = useMonitorStore((s) => s.dashboard);
  const tasks = dashboard?.tasks ?? [];
  const gauges = hostResourceGauges(useHostResources());

  return (
    <div className="mon-live-stack">
      <MonitorPanel title="資源">
        <ResourceGauges gauges={gauges} />
        <p className="mt-2 text-center text-[10px] text-[var(--console-faint)]">主機 CPU／記憶體／網路</p>
      </MonitorPanel>
      <TaskStackPanel tasks={tasks} statusStack={statusStack} onOpenTab={onOpenTab} />
      <ApiPoolCard feed={feed} onOpen={() => onOpenTab?.('llm')} />
      <CompanyCard
        feed={consoleFeed}
        onOpen={() => onOpenTab?.('agents')}
        onOpenAgent={onOpenAgent}
        onOpenTab={onOpenTab}
      />
    </div>
  );
}
