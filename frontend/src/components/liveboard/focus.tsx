/**
 * LiveBoard 首屏聚焦區：工作流軌、態勢／下一步／異常焦點卡與聚焦格。
 */
import { useMemo } from 'react';
import { requestRoleSettingsDesk } from '../../lib/agentUi';
import type { AnimLiveFeed } from '../../lib/animLive';
import {
  buildWorkflowSteps,
  collectLiveAnomalies,
  isLiveBoardTaskEmpty,
  pickNextWorkflowStep,
  type LiveAnomaly,
  type WorkflowStep,
} from '../../lib/liveBoardFocus';
import { hostResourceGauges } from '../../lib/monitorData';
import { useHostResources } from '../../lib/hostResources';
import { jumpToL0Kernel } from '../../lib/rahoUi';
import type { L0Snapshot } from '../../types';
import type { MonitorTab } from '../AppShell';
import { MonitorL0StatusChip, MonitorStatusDot, ResourceGauges } from '../ui/monitor';

export function WorkflowRail({
  steps,
  onOpenTab,
}: {
  steps: WorkflowStep[];
  onOpenTab?: (tab: MonitorTab) => void;
}) {
  const nextIdx = steps.findIndex((s) => !s.done);

  return (
    <div className="mon-workflow">
      <p className="mon-stack-section__label">工作流</p>
      {steps.map((s, i) => {
        const next = i === nextIdx;
        const tag = s.done ? '完成' : s.active ? '進行中' : next ? '下一步' : s.n;
        const tagClass = s.done
          ? 'mon-workflow__step-tag--done'
          : s.active || next
            ? 'mon-workflow__step-tag--active'
            : '';
        return (
          <button
            key={s.tab}
            type="button"
            onClick={() => (s.onClick ? s.onClick() : onOpenTab?.(s.tab))}
            className={`mon-workflow__step${next ? ' on' : ''}${s.done ? ' done' : ''}`}
          >
            <span className={`mon-workflow__step-tag ${tagClass}`}>{tag}</span>
            <span className="mon-workflow__step-label">{s.label}</span>
            <span className="mon-workflow__step-hint">{s.hint}</span>
          </button>
        );
      })}
    </div>
  );
}

export function SituationFocusCard({
  feed,
  l0Snapshot,
  connected,
}: {
  feed: AnimLiveFeed;
  l0Snapshot: L0Snapshot | null;
  connected: boolean;
}) {
  const gauges = hostResourceGauges(useHostResources());
  const running = feed.runningTasks + (feed.summary?.running_company_tasks ?? 0);

  return (
    <section className="mon-focus-card" data-testid="monitor-focus-situation" aria-labelledby="mon-focus-situation-title">
      <header className="mon-focus-card__head">
        <h2 id="mon-focus-situation-title" className="mon-focus-card__title">態勢</h2>
        <MonitorStatusDot tone={feed.live ? 'ok' : 'idle'} label={feed.live ? 'LIVE' : '待命'} />
      </header>
      <div className="mon-focus-card__body">
        <MonitorL0StatusChip snapshot={l0Snapshot} onClick={jumpToL0Kernel} />
        <div className="mon-focus-metrics">
          <div className="mon-focus-metric">
            <span className="mon-focus-metric__label">執行中任務</span>
            <span className="mon-focus-metric__value font-mono tabular-nums">{running}</span>
          </div>
          <div className="mon-focus-metric">
            <span className="mon-focus-metric__label">席位</span>
            <span className="mon-focus-metric__value font-mono tabular-nums">{feed.agents.length}</span>
          </div>
          <div className="mon-focus-metric">
            <span className="mon-focus-metric__label">連線</span>
            <span className="mon-focus-metric__value">{connected ? 'Hub 已連線' : '快照'}</span>
          </div>
        </div>
        <ResourceGauges gauges={gauges} />
        <p className="mt-2 text-center text-[10px] text-[var(--console-faint)]">主機實測</p>
      </div>
    </section>
  );
}

export function NextStepFocusCard({
  step,
  taskEmpty,
  onActivate,
}: {
  step: WorkflowStep | null;
  taskEmpty: boolean;
  onActivate: (step: WorkflowStep) => void;
}) {
  if (!step) {
    return (
      <section className="mon-focus-card mon-focus-card--next" data-testid="monitor-focus-next">
        <header className="mon-focus-card__head">
          <h2 className="mon-focus-card__title">下一步</h2>
          <MonitorStatusDot tone="ok" label="就緒" />
        </header>
        <div className="mon-focus-card__body">
          <p className="mon-focus-empty-copy">工作流步驟皆已完成，可隨時執行新任務。</p>
        </div>
      </section>
    );
  }

  const tag = step.done ? '完成' : step.active ? '進行中' : '下一步';
  const hero = taskEmpty && !step.active;

  return (
    <section
      className={`mon-focus-card mon-focus-card--next${hero ? ' mon-focus-card--hero' : ''}`}
      data-testid="monitor-focus-next"
      aria-labelledby="mon-focus-next-title"
    >
      <header className="mon-focus-card__head">
        <h2 id="mon-focus-next-title" className="mon-focus-card__title">下一步</h2>
        <span className="mon-focus-step-tag">{tag}</span>
      </header>
      <div className="mon-focus-card__body">
        {hero ? (
          <button type="button" className="mon-focus-cta" onClick={() => onActivate(step)}>
            <span className="mon-focus-cta__label">{step.label}</span>
            <span className="mon-focus-cta__hint">{step.hint}</span>
          </button>
        ) : (
          <button type="button" className="mon-focus-step-btn" onClick={() => onActivate(step)}>
            <span className="mon-focus-step-btn__label">{step.label}</span>
            <span className="mon-focus-step-btn__hint">{step.hint}</span>
          </button>
        )}
      </div>
    </section>
  );
}

export function AnomaliesFocusCard({
  anomalies,
  onJump,
  onOpenAlerts,
}: {
  anomalies: LiveAnomaly[];
  onJump: (a: LiveAnomaly) => void;
  onOpenAlerts?: () => void;
}) {
  return (
    <section className="mon-focus-card mon-focus-card--anomaly" data-testid="monitor-focus-anomaly" aria-labelledby="mon-focus-anomaly-title">
      <header className="mon-focus-card__head">
        <h2 id="mon-focus-anomaly-title" className="mon-focus-card__title">異常</h2>
        <MonitorStatusDot
          tone={anomalies.length ? 'warn' : 'ok'}
          label={anomalies.length ? `${anomalies.length} 項` : '無異常'}
        />
      </header>
      <div className="mon-focus-card__body">
        {anomalies.length === 0 ? (
          <p className="mon-focus-empty-copy">目前無需處理的異常。</p>
        ) : (
          <ul className="mon-focus-anomaly-list">
            {anomalies.slice(0, 5).map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  className={`mon-focus-anomaly-item mon-focus-anomaly-item--${a.tone}`}
                  onClick={() => onJump(a)}
                >
                  <span className="mon-focus-anomaly-item__title">{a.title}</span>
                  {a.hint ? <span className="mon-focus-anomaly-item__hint">{a.hint}</span> : null}
                </button>
              </li>
            ))}
          </ul>
        )}
        {onOpenAlerts ? (
          <button type="button" className="mon-focus-link" onClick={onOpenAlerts}>
            開啟警報
          </button>
        ) : null}
      </div>
    </section>
  );
}

export function LiveBoardFocusGrid({
  feed,
  l0Snapshot,
  connected,
  unhealthyKeys,
  capacityFull,
  cacheWarnText,
  taskCount,
  onOpenTab,
  onOpenAgent,
  onOpenAlerts,
}: {
  feed: AnimLiveFeed;
  l0Snapshot: L0Snapshot | null;
  connected: boolean;
  unhealthyKeys: number;
  capacityFull: boolean;
  cacheWarnText?: string;
  taskCount: number;
  onOpenTab?: (tab: MonitorTab) => void;
  onOpenAgent?: (id: string) => void;
  onOpenAlerts?: () => void;
}) {
  const steps = useMemo(
    () =>
      buildWorkflowSteps(feed, onOpenTab, () => {
        requestRoleSettingsDesk();
      }),
    [feed, onOpenTab],
  );
  const nextStep = pickNextWorkflowStep(steps);
  const taskEmpty = isLiveBoardTaskEmpty(feed, taskCount);
  const anomalies = useMemo(
    () =>
      collectLiveAnomalies({
        feed,
        connected,
        unhealthyKeys,
        capacityFull,
        cacheWarnText,
      }),
    [feed, connected, unhealthyKeys, capacityFull, cacheWarnText],
  );

  const activateStep = (step: WorkflowStep) => {
    if (step.onClick) step.onClick();
    else onOpenTab?.(step.tab);
  };

  const jumpAnomaly = (a: LiveAnomaly) => {
    if (a.tab && a.tab !== 'live') onOpenTab?.(a.tab);
    if (a.agentId) onOpenAgent?.(a.agentId);
  };

  return (
    <div className="mon-live-focus" data-testid="monitor-live-focus">
      <SituationFocusCard feed={feed} l0Snapshot={l0Snapshot} connected={connected} />
      <NextStepFocusCard step={nextStep} taskEmpty={taskEmpty} onActivate={activateStep} />
      <AnomaliesFocusCard anomalies={anomalies} onJump={jumpAnomaly} onOpenAlerts={onOpenAlerts} />
    </div>
  );
}
