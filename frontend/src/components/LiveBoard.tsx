/**
 * LiveBoard — EvoLoop 主監控總覽（monitor dashboard v3）。
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { fetchBillingOverview } from '../api/client';
import MonitorAlertMode from './monitor/MonitorAlertMode';
import {
  type AnimLiveFeed,
  budgetPct,
  buildReportLines,
  mapPhaseToPipelineIndex,
  pickActiveAgents,
  pickBusyAgents,
} from '../lib/animLive';
import { isLabLink, labSections, LAB_NAV_GROUPS, type LabNavEntry, type LabSubTab } from '../lib/labTabs';
import { filterAgentsByDesk, PIPELINE_STAGES, requestRoleSettingsDesk } from '../lib/agentUi';
import {
  buildActivityHeatmap,
  buildSparkSeries24,
  buildStatusStack,
  buildTaskDistributionMatrix,
  hostResourceGauges,
  taskPriority,
} from '../lib/monitorData';
import { useHostResources } from '../lib/hostResources';
import { navPathForTab } from '../lib/monitorTabs';
import {
  buildWorkflowSteps,
  collectLiveAnomalies,
  isLiveBoardTaskEmpty,
  pickNextWorkflowStep,
  type LiveAnomaly,
  type WorkflowStep,
} from '../lib/liveBoardFocus';
import { jumpToL0Kernel } from '../lib/rahoUi';
import type { MonitorTab } from './AppShell';
import IntegrationsStrip from './IntegrationsStrip';
import {
  ActivityHeatmap,
  KpiSparkCard,
  MiniProgressBar,
  MonitorKpiGrid,
  MonitorLinkButton,
  MonitorPanel,
  MonitorStatusDot,
  MonitorL0StatusChip,
  MonitorStatusStrip,
  MonitorWarnBar,
  PipelineTimeline,
  ResourceGauges,
  StackBar,
  TaskDistributionMatrix,
  TaskPriorityCard,
} from './ui/monitor';
import type { MonitorStatusTone } from './ui/monitor';
import { PanelShell } from './ui/ConsoleLayout';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { useMonitorStore } from '../stores/monitorStore';
import type { L0Snapshot, TaskSummary } from '../types';

export type LiveBoardDensity = 'page' | 'dock';

export interface LiveBoardNav {
  onOpenTab?: (tab: MonitorTab) => void;
  onOpenLab?: (sub: LabSubTab) => void;
  onOpenTraces?: () => void;
  onOpenAgent?: (id: string) => void;
}

function liveTone(feed: AnimLiveFeed): MonitorStatusTone {
  return feed.live ? 'ok' : 'idle';
}

function WorkflowRail({
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

function SituationFocusCard({
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
            <span className="mon-focus-metric__label">角色</span>
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

function NextStepFocusCard({
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

function AnomaliesFocusCard({
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
            開啟監控模式
          </button>
        ) : null}
      </div>
    </section>
  );
}

function LiveBoardFocusGrid({
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

function LiveBoardDetailsToggle({
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

function PipelineCard({
  feed,
  backgroundPhase,
  dock,
  onOpen,
}: {
  feed: AnimLiveFeed;
  backgroundPhase?: string | null;
  dock?: boolean;
  onOpen?: () => void;
}) {
  const phase = feed.streamPhase || feed.taskPhase || backgroundPhase || null;
  const liveIdx = mapPhaseToPipelineIndex(phase);
  const nodes = PIPELINE_STAGES.map((n, i) => ({
    id: n.id,
    label: n.label,
    state: liveIdx == null
      ? ('pending' as const)
      : i < liveIdx
        ? ('done' as const)
        : i === liveIdx
          ? ('active' as const)
          : ('pending' as const),
    timingMs: liveIdx != null && i === liveIdx && feed.live ? 120 : liveIdx != null && i < liveIdx ? 80 + i * 40 : null,
  }));

  return (
    <MonitorPanel
      title="管線"
      accessory={
        <>
          <MonitorStatusDot tone={liveIdx != null ? 'info' : 'idle'} label={phase ? String(phase) : '待命'} />
          {onOpen ? <MonitorLinkButton onClick={onOpen} /> : null}
        </>
      }
    >
      <div className={dock ? 'py-1' : 'py-2'}>
        <PipelineTimeline nodes={nodes} />
      </div>
    </MonitorPanel>
  );
}

function CompanyCard({
  feed,
  dock,
  onOpen,
  onOpenAgent,
  onOpenTab,
}: {
  feed: AnimLiveFeed;
  dock?: boolean;
  onOpen?: () => void;
  onOpenAgent?: (id: string) => void;
  onOpenTab?: (tab: MonitorTab) => void;
}) {
  const busy = useMemo(() => pickBusyAgents(feed.agents, dock ? 4 : 5), [feed.agents, dock]);
  const active = useMemo(() => pickActiveAgents(feed.agents, 6), [feed.agents]);
  const tone: MonitorStatusTone = active.length ? 'ok' : busy.length ? 'warn' : 'idle';

  return (
    <MonitorPanel
      title="協作"
      accessory={
        <>
          <MonitorStatusDot
            tone={tone}
            label={active.length ? `${active.length} 執行` : busy.length ? `${busy.length} 佇列` : '空閒'}
          />
          {onOpen ? <MonitorLinkButton onClick={onOpen} label="角色／質詢" /> : null}
          {onOpenTab ? <MonitorLinkButton onClick={() => onOpenTab('memory')} label="L0" /> : null}
          {onOpenTab ? <MonitorLinkButton onClick={() => onOpenTab('integrations')} label="整合" /> : null}
        </>
      }
      scroll={busy.length > (dock ? 3 : 4)}
      className={dock ? 'max-h-[180px]' : 'max-h-[240px]'}
    >
      {busy.length === 0 ? (
        <div className="py-4 text-center">
          <p className="text-[12px] text-[var(--console-faint)]">無忙碌角色</p>
          {feed.agents.some((a) => a.preferred_model || a.preferred_provider) ? (
            <p className="mt-1 text-[11px] text-[var(--console-sub)]">
              {feed.agents.filter((a) => a.preferred_model || a.preferred_provider).length} 席已指定模型
            </p>
          ) : onOpen ? (
            <button
              type="button"
              onClick={() => {
                requestRoleSettingsDesk();
                onOpen();
              }}
              className="mon-link-btn mt-2 text-[11px] font-medium"
            >
              指定模型與 Token
            </button>
          ) : null}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {busy.map((a) => {
            const hot = active.some((x) => x.id === a.id);
            const pct = Math.min(
              100,
              Math.round((a.capacity_used ?? 0) * 100) || (a.executing ? 55 : a.queue ? 20 : 8),
            );
            return (
              <div
                key={a.id}
                className={onOpenAgent ? 'cursor-pointer rounded-lg hover:bg-[var(--console-card-elevated)]' : ''}
                onClick={() => onOpenAgent?.(a.id)}
                onKeyDown={(e) => {
                  if (onOpenAgent && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault();
                    onOpenAgent(a.id);
                  }
                }}
                role={onOpenAgent ? 'button' : undefined}
                tabIndex={onOpenAgent ? 0 : undefined}
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <p className="truncate text-[12px] font-semibold text-[var(--console-ink)]">{a.name}</p>
                  <MonitorStatusDot tone={hot ? 'ok' : a.status === 'error' ? 'err' : 'warn'} label={`${pct}%`} />
                </div>
                <MiniProgressBar value={pct} hot={hot} good={a.status !== 'error'} />
              </div>
            );
          })}
        </div>
      )}
    </MonitorPanel>
  );
}

function BudgetCard({
  feed,
  dock,
  onOpen,
}: {
  feed: AnimLiveFeed;
  dock?: boolean;
  onOpen?: () => void;
}) {
  const b = budgetPct(feed.summary);

  return (
    <MonitorPanel
      title="預算"
      accessory={
        <>
          <MonitorStatusDot
            tone={b.totalUsd > 0 ? 'info' : 'idle'}
            label={b.totalUsd > 0 ? `$${b.totalUsd.toFixed(3)}` : '無用量'}
          />
          {onOpen ? <MonitorLinkButton onClick={onOpen} label="用量" /> : null}
        </>
      }
    >
      <ResourceGauges
        gauges={[
          { label: 'API', pct: b.apiPct, color: 'var(--console-blue)' },
          { label: '雲資源', pct: b.cloudPct, color: 'var(--console-amber)' },
        ]}
      />
      {b.totalUsd > 0 && !dock ? (
        <p className="mt-3 text-center text-[10px] text-[var(--console-faint)]">
          API ${b.apiUsd.toFixed(3)} · 雲 ${b.cloudUsd.toFixed(3)}
        </p>
      ) : null}
    </MonitorPanel>
  );
}

function SystemMetricsCard({
  feed,
  onOpen,
}: {
  feed: AnimLiveFeed;
  onOpen?: () => void;
}) {
  const opt = feed.optimization;
  const hitPct = Math.round((opt?.llm_cache.hit_rate ?? 0) * 100);
  const traceCount = opt?.trace.trace_count ?? 0;
  const successRate = opt?.system_stats?.success_rate ?? 0;
  const satisfaction = Math.round((opt?.user_feedback?.satisfaction_rate ?? 0) * 100);
  const tone: MonitorStatusTone = hitPct >= 30 || traceCount > 0 ? 'ok' : 'idle';

  return (
    <MonitorPanel
      title="運行指標"
      accessory={
        <>
          <MonitorStatusDot tone={tone} label={hitPct >= 30 ? '快取活躍' : '累積中'} />
          {onOpen ? <MonitorLinkButton onClick={onOpen} /> : null}
        </>
      }
    >
      <MonitorKpiGrid className="!mb-0 !grid-cols-3">
        <KpiSparkCard label="快取" value={`${hitPct}%`} size="lg" accent={hitPct >= 30} />
        <KpiSparkCard label="成功率" value={`${successRate}%`} size="lg" />
        <KpiSparkCard label="Trace" value={String(traceCount)} size="lg" />
      </MonitorKpiGrid>
      {satisfaction > 0 && (
        <p className="text-center text-[10px] text-[var(--console-sub)]">滿意度 {satisfaction}%</p>
      )}
    </MonitorPanel>
  );
}

function EventsCard({
  feed,
  dock,
  onOpen,
}: {
  feed: AnimLiveFeed;
  dock?: boolean;
  onOpen?: () => void;
}) {
  const lines = useMemo(() => buildReportLines(feed.agents, dock ? 4 : 6), [feed.agents, dock]);

  return (
    <MonitorPanel
      title="事件"
      accessory={
        <>
          <MonitorStatusDot tone={lines.length ? 'ok' : 'idle'} label={lines.length ? `${lines.length}` : '無'} />
          {onOpen ? <MonitorLinkButton onClick={onOpen} label="軌跡" /> : null}
        </>
      }
      className={dock ? 'max-h-[200px]' : 'max-h-[260px]'}
      scroll={lines.length > (dock ? 3 : 4)}
    >
      {lines.length === 0 ? (
        <p className="py-8 text-center text-[12px] text-[var(--console-faint)]">等待事件</p>
      ) : (
        <ul className="divide-y divide-[var(--console-line)]">
          {lines.map((s) => (
            <li key={s.id} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
              <span className="mon-status-dot__mark mon-status-dot__mark--info mt-1.5 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[11px] font-semibold text-[var(--console-blue)]">{s.role}</p>
                <p className="mt-0.5 text-[12px] leading-snug text-[var(--console-ink)]">{s.line}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </MonitorPanel>
  );
}

function ApiPoolCard({ feed, onOpen }: { feed: AnimLiveFeed; onOpen?: () => void }) {
  const ops = feed.llmOps;
  const routes = ops?.api_routes ?? [];
  const configured = routes.filter((r) => r.configured && r.enabled);
  const strategy = ops?.route_strategy || 'role_preferred';
  const modelCount = ops?.allowed_models.length ?? 0;
  const tone: MonitorStatusTone = !ops ? 'idle' : configured.length ? 'ok' : 'warn';

  return (
    <MonitorPanel title="API 池" accessory={onOpen ? <MonitorLinkButton onClick={onOpen} label="管理" /> : undefined}>
      {!ops ? (
        <p className="py-4 text-center text-[12px] text-[var(--console-faint)]">同步中…</p>
      ) : routes.length === 0 && !ops.configured ? (
        <div className="py-4 text-center">
          <p className="text-[12px] text-[var(--console-sub)]">尚未配置 API</p>
          {onOpen ? (
            <MonitorLinkButton onClick={onOpen} label={`前往 ${navPathForTab('llm')}`} />
          ) : null}
        </div>
      ) : (
        <div className="space-y-2 py-1">
          <div className="flex items-center justify-between text-[11px] text-[var(--console-sub)]">
            <MonitorStatusDot
              tone={tone}
              label={
                routes.length
                  ? `${configured.length}/${routes.length} 啟用`
                  : ops.configured
                    ? '單一 API'
                    : '未配置'
              }
            />
            <span>
              {modelCount} 模型 · {strategy}
            </span>
          </div>
          <ul className="divide-y divide-[var(--console-line)]">
            {(routes.length
              ? routes
              : [
                  {
                    id: 'primary',
                    name: ops.provider_label || '預設 API',
                    model: ops.model,
                    allowed_models: ops.allowed_models,
                    configured: ops.configured,
                    enabled: true,
                  },
                ]
            )
              .slice(0, 4)
              .map((route) => (
                <li key={route.id} className="flex items-center justify-between gap-2 py-1.5 first:pt-0">
                  <button
                    type="button"
                    className="min-w-0 truncate text-left text-[12px] font-medium text-[var(--console-ink)] hover:text-[var(--console-blue)]"
                    onClick={onOpen}
                  >
                    {route.name}
                  </button>
                  <span className="shrink-0 font-mono text-[10px] tabular-nums text-[var(--console-sub)]">
                    {route.model || `${route.allowed_models.length} 模`}
                  </span>
                </li>
              ))}
          </ul>
        </div>
      )}
    </MonitorPanel>
  );
}

function ExternalIntegrationsCard({
  dock,
  onOpenTab,
}: {
  dock?: boolean;
  onOpenTab?: (tab: MonitorTab) => void;
}) {
  return (
    <MonitorPanel
      title="外部整合"
      accessory={
        onOpenTab ? (
          <MonitorLinkButton onClick={() => onOpenTab('integrations')} label="面板" />
        ) : (
          <MonitorLinkButton href="#/monitor/integrations" label="面板" />
        )
      }
      className={dock ? '' : 'mon-span-2'}
    >
      <IntegrationsStrip density={dock ? 'compact' : 'comfortable'} showSummary={false} showGroups={!dock} />
      <p className="mt-2 text-[10px] leading-relaxed text-[var(--console-faint)]">
        MemOS 記憶 · OpenViking 分層上下文 · WeKnora 知識 · Yao 任務板 · Ouroboros 閘門 · OpenPencil 設計。預設關閉，顯式啟用。
      </p>
    </MonitorPanel>
  );
}

function labChip(
  item: LabNavEntry,
  chipClass: string,
  onOpenLab?: (sub: LabSubTab) => void,
) {
  if (isLabLink(item)) {
    return (
      <a key={item.key} href={item.href} className={chipClass} title={item.hint}>
        {item.label}
      </a>
    );
  }
  return onOpenLab ? (
    <button
      key={item.key}
      type="button"
      onClick={() => onOpenLab(item.key)}
      className={chipClass}
      title={item.upstream?.name ?? item.hint}
    >
      {item.label}
    </button>
  ) : (
    <a
      key={item.key}
      href={item.key === 'prompt' ? '#/monitor/lab' : `#/monitor/lab/${item.key}`}
      className={chipClass}
      title={item.upstream?.name ?? item.hint}
    >
      {item.label}
    </a>
  );
}

function LabToolsCard({
  dock,
  onOpenLab,
}: {
  dock?: boolean;
  onOpenLab?: (sub: LabSubTab) => void;
}) {
  const chipClass =
    'rounded-full border border-[var(--console-line)] bg-[var(--console-card-elevated)] px-3 py-1.5 text-[11px] font-medium text-[var(--console-ink)] transition-colors hover:border-[color-mix(in_srgb,var(--console-accent)_40%,transparent)] hover:bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)]';

  return (
    <MonitorPanel
      title="實驗室工具"
      accessory={
        onOpenLab ? (
          <MonitorLinkButton onClick={() => onOpenLab('prompt')} label="實驗室" />
        ) : (
          <MonitorLinkButton href="#/monitor/lab" label="實驗室" />
        )
      }
      className={dock ? '' : 'mon-span-2'}
    >
      <div className="space-y-3">
        {LAB_NAV_GROUPS.map((group) => (
          <div key={group.id}>
            <p className="mb-1.5 text-[10px] font-semibold tracking-wide text-[var(--console-faint)]">{group.label}</p>
            <div className="space-y-2">
              {labSections(group).map((section) => (
                <div key={section.id}>
                  {section.label ? (
                    <p className="mb-1 text-[10px] text-[var(--console-faint)]">{section.label}</p>
                  ) : null}
                  <div className="flex flex-wrap gap-2">
                    {section.items.map((item) => labChip(item, chipClass, onOpenLab))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-[var(--console-faint)]">
        核心的開發組件 · minecraft組件 · 價格分析探針組件 · 整合
      </p>
    </MonitorPanel>
  );
}

function OverviewKpiRow({ feed }: { feed: AnimLiveFeed }) {
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
        { label: '角色', value: String(feed.agents.length) },
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

function TaskStackPanel({
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

function CenterMain({
  feed,
  consoleFeed,
  backgroundPhase,
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
  backgroundPhase?: string | null;
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
          <div className="mon-span-2">
            <PipelineCard feed={feed} backgroundPhase={backgroundPhase} dock onOpen={() => onOpenTab?.('pipeline')} />
          </div>
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
          <PipelineCard feed={feed} backgroundPhase={backgroundPhase} onOpen={() => onOpenTab?.('pipeline')} />
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

function RightRailContent({
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

export default function LiveBoard({
  feed,
  backgroundPhase,
  l0Snapshot = null,
  density = 'page',
  liteShell = false,
  onOpenLab,
  onOpenTab,
  onOpenTraces,
  onOpenAgent,
}: {
  feed: AnimLiveFeed;
  backgroundPhase?: string | null;
  l0Snapshot?: L0Snapshot | null;
  density?: LiveBoardDensity;
  liteShell?: boolean;
} & LiveBoardNav) {
  const { t } = useTranslation();
  const [alertMode, setAlertMode] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [unhealthyKeys, setUnhealthyKeys] = useState(0);
  const dock = density === 'dock';
  const isMobile = useMediaQuery('(max-width: 767px)', false);

  useEffect(() => {
    if (dock) return;
    fetchBillingOverview()
      .then((o) => setUnhealthyKeys(o.unhealthy_keys_count))
      .catch(() => setUnhealthyKeys(0));
  }, [dock]);

  const dashboard = useMonitorStore((s) => s.dashboard);
  const connected = useMonitorStore((s) => s.connected);
  const consoleFeed = useMemo(
    () => ({ ...feed, agents: filterAgentsByDesk(feed.agents, 'console') }),
    [feed],
  );
  const taskMatrix = useMemo(
    () => buildTaskDistributionMatrix(dashboard?.tasks ?? []),
    [dashboard?.tasks],
  );
  const statusStack = useMemo(
    () => buildStatusStack(dashboard?.stats ?? {}),
    [dashboard?.stats],
  );
  const updated = consoleFeed.updatedAt
    ? new Date(consoleFeed.updatedAt).toLocaleTimeString('zh-TW', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : null;

  const opt = feed.optimization;
  const edge = opt?.edge_cache ?? opt?.opc_edge;
  const cacheCapPct = edge?.max_size ? ((edge?.entry_count ?? 0) / edge.max_size) * 100 : 0;
  const capacityFull = cacheCapPct >= 100;
  const cacheWarnText = capacityFull
    ? `⚠ 快取容量 ${Math.round(cacheCapPct)}% — 建議清理（${edge?.entry_count ?? 0}/${edge?.max_size ?? 512}）`
    : undefined;

  const handleAlertJump = (tab: MonitorTab, detail?: string) => {
    onOpenTab?.(tab);
    if (detail && tab === 'agents') onOpenAgent?.(detail);
  };

  const statusStripActions = (
    <>
      {!liteShell ? (
        <button
          type="button"
          onClick={() => setAlertMode(true)}
          className="mon-alert-btn"
          data-testid="monitor-alert-mode-toggle"
        >
          {t('monitorAlert.toggle')}
        </button>
      ) : null}
      <MonitorStatusDot tone={liveTone(feed)} label={feed.live ? 'LIVE' : 'IDLE'} />
    </>
  );

  const statusStripLeading = <span className="mon-live-status__eyebrow">即時總覽</span>;

  const workflowSteps = useMemo(
    () =>
      buildWorkflowSteps(consoleFeed, onOpenTab, () => {
        requestRoleSettingsDesk();
      }),
    [consoleFeed, onOpenTab],
  );

  const taskCount = dashboard?.tasks?.length ?? 0;

  const focusGrid = (
    <LiveBoardFocusGrid
      feed={feed}
      l0Snapshot={l0Snapshot}
      connected={connected}
      unhealthyKeys={unhealthyKeys}
      capacityFull={capacityFull}
      cacheWarnText={cacheWarnText}
      taskCount={taskCount}
      onOpenTab={onOpenTab}
      onOpenAgent={onOpenAgent}
      onOpenAlerts={liteShell ? undefined : () => setAlertMode(true)}
    />
  );

  const statusStrip = !dock ? (
    <MonitorStatusStrip
      leading={statusStripLeading}
      actions={statusStripActions}
      meta={updated ? <span className="font-mono tabular-nums">{updated}</span> : null}
    />
  ) : null;

  const liteHint = liteShell ? (
    <p className="mon-live-hint" title={t('mobileShell.alertModeDesktop')}>
      {t('mobileShell.alertModeDesktop')}
    </p>
  ) : null;

  const center = (
    <CenterMain
      feed={feed}
      consoleFeed={consoleFeed}
      backgroundPhase={backgroundPhase}
      taskMatrix={taskMatrix}
      statusStack={statusStack}
      capacityFull={capacityFull}
      cacheWarnText={cacheWarnText}
      dock={dock}
      liteShell={liteShell}
      onOpenTab={onOpenTab}
      onOpenTraces={onOpenTraces}
      onOpenAgent={onOpenAgent}
      onOpenLab={onOpenLab}
      showTaskStack={false}
    />
  );

  const right = (
    <RightRailContent
      feed={feed}
      consoleFeed={consoleFeed}
      statusStack={statusStack}
      onOpenTab={onOpenTab}
      onOpenAgent={onOpenAgent}
    />
  );

  const detailsBody = (
    <>
      <WorkflowRail steps={workflowSteps} onOpenTab={onOpenTab} />
      {center}
      {right}
    </>
  );

  const detailsPanel = !dock && !liteShell ? (
    <LiveBoardDetailsToggle open={detailsOpen} onToggle={() => setDetailsOpen((v) => !v)}>
      {detailsBody}
    </LiveBoardDetailsToggle>
  ) : (
    detailsBody
  );

  if (dock) {
    return (
      <div className="mon-live-shell flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-[var(--console-line)]">
        <MonitorAlertMode
          open={alertMode && !liteShell}
          onClose={() => setAlertMode(false)}
          onJump={handleAlertJump}
          unhealthyKeysCount={unhealthyKeys}
        />
        <div className="mon-live-mobile-scroll">
          <div className="mb-2 flex items-center gap-2">
            <MonitorStatusDot tone={liveTone(feed)} label={feed.live ? 'LIVE' : 'IDLE'} />
            {updated ? <span className="font-mono text-[10px] tabular-nums text-[var(--console-faint)]">{updated}</span> : null}
          </div>
          {focusGrid}
          {center}
        </div>
      </div>
    );
  }

  if (isMobile && !dock) {
    return (
      <PanelShell scroll={false}>
        <div className="mon-live-shell">
          <MonitorAlertMode
            open={alertMode && !liteShell}
            onClose={() => setAlertMode(false)}
            onJump={handleAlertJump}
            unhealthyKeysCount={unhealthyKeys}
          />
          {statusStrip}
          {liteHint}
          <div className="mon-live-mobile-scroll">
            {focusGrid}
            {detailsPanel}
          </div>
        </div>
      </PanelShell>
    );
  }

  return (
    <PanelShell scroll={false}>
      <div className="mon-live-shell">
        <MonitorAlertMode
          open={alertMode && !liteShell}
          onClose={() => setAlertMode(false)}
          onJump={handleAlertJump}
          unhealthyKeysCount={unhealthyKeys}
        />
        {statusStrip}
        {liteHint}
        <div className="mon-live-mobile-scroll mon-live-mobile-scroll--desktop">
          {focusGrid}
          {detailsPanel}
        </div>
      </div>
    </PanelShell>
  );
}
