/**
 * LiveBoard — 控制台總覽（Apple 控制中心風格）。
 * 卡片可跳到對應分頁：API 路由／角色／任務／計費，避免功能孤立。
 */
import { useMemo } from 'react';
import type { ReactNode } from 'react';
import {
  type AnimLiveFeed,
  budgetPct,
  buildReportLines,
  mapPhaseToPipelineIndex,
  pickActiveAgents,
  pickBusyAgents,
} from '../lib/animLive';
import { LAB_INTEGRATION_TABS, type LabSubTab } from '../lib/labTabs';
import { filterAgentsByDesk, PIPELINE_STAGES, requestRoleSettingsDesk } from '../lib/agentUi';
import { buildStatusStack, buildTaskDistributionMatrix } from '../lib/monitorData';
import { navPathForTab } from '../lib/monitorTabs';
import type { MonitorTab } from './AppShell';
import IntegrationsStrip from './IntegrationsStrip';
import { consoleLayout } from './ui/ConsoleLayout';
import { KpiSparkCard, PipelineTimeline, StackBar, TaskDistributionMatrix } from './ui/monitor';
import { useMonitorStore } from '../stores/monitorStore';

const BLUE = 'var(--console-accent)';
const GREEN = 'var(--console-green)';
const ORANGE = 'var(--console-amber)';
const RED = 'var(--console-danger)';
const GRAY = 'var(--console-sub)';

export type LiveBoardDensity = 'page' | 'dock';

export interface LiveBoardNav {
  onOpenTab?: (tab: MonitorTab) => void;
  onOpenLab?: (sub: LabSubTab) => void;
  onOpenTraces?: () => void;
  onOpenAgent?: (id: string) => void;
}

function GoBtn({ onClick, label = '前往' }: { onClick: () => void; label?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-[10px] font-bold console-status-accent hover:underline"
    >
      {label}
    </button>
  );
}

function FrostCard({
  title,
  accessory,
  className = '',
  bodyClassName = '',
  scroll = false,
  children,
}: {
  title: string;
  accessory?: ReactNode;
  className?: string;
  bodyClassName?: string;
  scroll?: boolean;
  children: ReactNode;
}) {
  return (
    <section className={`lb-frost-card ${className}`}>
      <header className="lb-card-head">
        <h2 className="lb-card-title">{title}</h2>
        {accessory}
      </header>
      <div className={`lb-card-body ${scroll ? '' : 'lb-card-body--static'} ${bodyClassName}`}>
        {children}
      </div>
    </section>
  );
}

function WorkflowStrip({
  feed,
  onOpenTab,
}: {
  feed: AnimLiveFeed;
  onOpenTab?: (tab: MonitorTab) => void;
}) {
  const routes = feed.llmOps?.api_routes ?? [];
  const apiReady =
    routes.some((r) => r.configured && r.enabled) || Boolean(feed.llmOps?.configured);
  const pinned = feed.agents.filter((a) => Boolean(a.preferred_model || a.preferred_provider)).length;
  const running = feed.runningTasks > 0 || feed.live;
  const steps: Array<{
    n: string;
    label: string;
    hint: string;
    tab: MonitorTab;
    done: boolean;
    onClick?: () => void;
  }> = [
    {
      n: '1',
      label: '配置 API',
      hint: apiReady ? `${routes.length || 1} 組可用` : '金鑰與模型目錄',
      tab: 'llm',
      done: apiReady,
    },
    {
      n: '2',
      label: '指定角色',
      hint: pinned ? `${pinned} 席已指定` : '模型與 Token',
      tab: 'agents',
      done: pinned > 0,
      onClick: () => {
        requestRoleSettingsDesk();
        onOpenTab?.('agents');
      },
    },
    {
      n: '3',
      label: '執行任務',
      hint: running ? '進行中' : '佇列與進度',
      tab: 'tasks',
      done: running,
    },
    {
      n: '4',
      label: '計費用量',
      hint: 'AI 與 Docker 成本',
      tab: 'billing',
      done: false,
    },
  ];
  const nextIdx = steps.findIndex((s) => !s.done);
  return (
    <div className="mb-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
      {steps.map((s, i) => {
        const next = i === nextIdx;
        return (
          <button
            key={s.tab}
            type="button"
            onClick={() => (s.onClick ? s.onClick() : onOpenTab?.(s.tab))}
            className={`rounded-2xl border px-3 py-2.5 text-left transition-colors ${
              next
                ? 'border-[color-mix(in_srgb,var(--console-accent)_50%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)]'
                : s.done
                  ? 'border-white/[0.08] bg-[var(--console-card)]'
                  : 'border-[var(--console-line)] bg-[var(--console-card)] hover:border-[color-mix(in_srgb,var(--console-accent)_40%,transparent)]'
            }`}
          >
            <p
              className={`text-[10px] font-bold uppercase tracking-wider ${
                next ? 'console-status-blue' : s.done ? 'console-status-green' : 'text-[var(--console-faint)]'
              }`}
            >
              {s.done ? '完成' : next ? '下一步' : s.n}
            </p>
            <p className="mt-0.5 text-[13px] font-semibold text-[var(--console-ink)]">{s.label}</p>
            <p className="text-[10px] text-[var(--console-sub)]">{s.hint}</p>
          </button>
        );
      })}
    </div>
  );
}

function StatusDot({ color, label }: { color: string; label: string }) {
  const tone =
    color === GREEN
      ? 'apple-dot apple-dot--ok'
      : color === ORANGE
        ? 'apple-dot apple-dot--warn'
        : color === RED
          ? 'apple-dot apple-dot--err'
          : color === BLUE
            ? 'apple-dot apple-dot--info'
            : 'apple-dot';
  return (
    <span className="inline-flex items-center gap-1.5 text-[10px] text-[var(--console-sub)]">
      <span className={tone} style={tone === 'apple-dot' ? { background: color } : undefined} />
      {label}
    </span>
  );
}

function RingMetric({
  value,
  max = 100,
  label,
  color,
  sub,
  size = 80,
}: {
  value: number;
  max?: number;
  label: string;
  color: string;
  sub?: string;
  size?: number;
}) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  const r = 34;
  const c = 2 * Math.PI * r;
  const dash = (pct / 100) * c;
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative" style={{ height: size, width: size }}>
        <svg viewBox="0 0 80 80" className="h-full w-full -rotate-90">
          <circle cx="40" cy="40" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="6" />
          <circle
            cx="40"
            cy="40"
            r={r}
            fill="none"
            stroke={color}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${c - dash}`}
            className="transition-[stroke-dasharray] duration-500 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="apple-data text-[16px] text-white">{pct}%</span>
        </div>
      </div>
      <p className="text-[12px] font-bold text-[var(--console-ink)]">{label}</p>
      {sub && <p className="apple-data text-[10px] text-[var(--console-sub)]">{sub}</p>}
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
    state: liveIdx == null ? 'pending' as const : i < liveIdx ? 'done' as const : i === liveIdx ? 'active' as const : 'pending' as const,
    timingMs: liveIdx != null && i === liveIdx && feed.live ? 120 : liveIdx != null && i < liveIdx ? 80 + i * 40 : null,
  }));

  return (
    <FrostCard
      title="管線"
      accessory={
        <span className="flex items-center gap-2">
          <StatusDot color={liveIdx != null ? BLUE : GRAY} label={phase ? String(phase) : '待命'} />
          {onOpen ? <GoBtn onClick={onOpen} /> : null}
        </span>
      }
    >
      <div className={dock ? 'py-1' : 'py-3'}>
        <PipelineTimeline nodes={nodes} />
      </div>
    </FrostCard>
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

  return (
    <FrostCard
      title="協作"
      accessory={
        <span className="flex items-center gap-2">
          <StatusDot
            color={active.length ? GREEN : busy.length ? ORANGE : GRAY}
            label={active.length ? `${active.length} 執行` : busy.length ? `${busy.length} 佇列` : '空閒'}
          />
          {onOpen ? <GoBtn onClick={onOpen} label="角色／質詢" /> : null}
          {onOpenTab ? <GoBtn onClick={() => onOpenTab('memory')} label="L0" /> : null}
          {onOpenTab ? <GoBtn onClick={() => onOpenTab('integrations')} label="整合" /> : null}
        </span>
      }
      className={dock ? 'max-h-[180px]' : 'max-h-[240px]'}
      scroll={busy.length > (dock ? 3 : 4)}
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
              className="mt-2 text-[11px] font-medium console-status-accent hover:underline"
            >
              指定模型與 Token
            </button>
          ) : null}
        </div>
      ) : (
        <div className="space-y-4">
          {busy.map((a) => {
            const hot = active.some((x) => x.id === a.id);
            const pct = Math.min(
              100,
              Math.round((a.capacity_used ?? 0) * 100) || (a.executing ? 55 : a.queue ? 20 : 8),
            );
            return (
              <div
                key={a.id}
                className={`flex items-center gap-3 ${onOpenAgent ? 'cursor-pointer rounded-lg hover:bg-white/[0.04]' : ''}`}
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
                <span
                  className="apple-dot shrink-0"
                  style={{
                    background: hot ? GREEN : a.status === 'error' ? RED : ORANGE,
                    boxShadow: hot ? `0 0 0 2px ${GREEN}33, 0 0 12px ${GREEN}66` : undefined,
                  }}
                />
                <div className="min-w-0 flex-1">
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <p className="truncate text-[12px] font-bold text-[var(--console-ink)]">{a.name}</p>
                    <span className="apple-data shrink-0 text-[10px] text-[var(--console-sub)]">{pct}%</span>
                  </div>
                  <div className="h-1 overflow-hidden rounded-full bg-white/[0.08]">
                    <div
                      className="h-full rounded-full transition-[width] duration-500"
                      style={{
                        width: `${pct}%`,
                        background: hot ? GREEN : a.status === 'error' ? RED : BLUE,
                      }}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </FrostCard>
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
    <FrostCard
      title="預算"
      accessory={
        <span className="flex items-center gap-2">
          <StatusDot
            color={b.totalUsd > 0 ? BLUE : GRAY}
            label={b.totalUsd > 0 ? `$${b.totalUsd.toFixed(3)}` : '無用量'}
          />
          {onOpen ? <GoBtn onClick={onOpen} label="用量" /> : null}
        </span>
      }
    >
      <div className={`flex items-center justify-around ${dock ? 'py-1' : 'py-2'}`}>
        <RingMetric
          value={b.apiPct}
          label="API"
          color={BLUE}
          size={dock ? 60 : 80}
          sub={b.totalUsd > 0 ? `$${b.apiUsd.toFixed(3)}` : '—'}
        />
        <RingMetric
          value={b.cloudPct}
          label="雲資源"
          color={ORANGE}
          size={dock ? 60 : 80}
          sub={b.totalUsd > 0 ? `$${b.cloudUsd.toFixed(3)}` : '—'}
        />
      </div>
    </FrostCard>
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
  const tone = hitPct >= 30 || traceCount > 0 ? GREEN : GRAY;

  return (
    <FrostCard
      title="運行指標"
      accessory={
        <span className="flex items-center gap-2">
          <StatusDot color={tone} label={hitPct >= 30 ? '快取活躍' : '累積中'} />
          {onOpen ? <GoBtn onClick={onOpen} /> : null}
        </span>
      }
    >
      <div className="grid grid-cols-1 gap-4 py-2 sm:grid-cols-3">
        {[
          { label: '快取', value: `${hitPct}%`, c: hitPct >= 30 ? GREEN : GRAY },
          { label: '成功率', value: `${successRate}%`, c: successRate >= 80 ? GREEN : ORANGE },
          { label: 'Trace', value: String(traceCount), c: traceCount > 0 ? BLUE : GRAY },
        ].map((cell) => (
          <div key={cell.label} className="text-center">
            <p className="apple-title !normal-case !tracking-normal">{cell.label}</p>
            <p className="apple-data mt-2 text-[20px]" style={{ color: cell.c }}>
              {cell.value}
            </p>
          </div>
        ))}
      </div>
      {satisfaction > 0 && (
        <p className="mt-1 text-center text-[10px] text-[var(--console-sub)]">滿意度 {satisfaction}%</p>
      )}
    </FrostCard>
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
    <FrostCard
      title="事件"
      accessory={
        <span className="flex items-center gap-2">
          <StatusDot color={lines.length ? GREEN : GRAY} label={lines.length ? `${lines.length}` : '無'} />
          {onOpen ? <GoBtn onClick={onOpen} label="軌跡" /> : null}
        </span>
      }
      className={dock ? 'max-h-[200px]' : 'max-h-[260px]'}
      scroll={lines.length > (dock ? 3 : 4)}
    >
      {lines.length === 0 ? (
        <p className="py-8 text-center text-[12px] text-[var(--console-faint)]">等待事件</p>
      ) : (
        <ul className="divide-y divide-white/[0.06]">
          {lines.map((s) => (
            <li key={s.id} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
              <span
                className="apple-dot mt-1.5 shrink-0"
                style={{
                  background: s.accent ?? BLUE,
                  boxShadow: `0 0 0 2px ${(s.accent ?? BLUE)}33, 0 0 10px ${(s.accent ?? BLUE)}55`,
                }}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[11px] font-bold" style={{ color: s.accent ?? BLUE }}>
                  {s.role}
                </p>
                <p className="mt-0.5 text-[12px] font-normal leading-snug text-[var(--console-ink)]">{s.line}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </FrostCard>
  );
}

function ApiPoolCard({ feed, onOpen }: { feed: AnimLiveFeed; onOpen?: () => void }) {
  const ops = feed.llmOps;
  const routes = ops?.api_routes ?? [];
  const configured = routes.filter((r) => r.configured && r.enabled);
  const strategy = ops?.route_strategy || 'role_preferred';
  const modelCount = ops?.allowed_models.length ?? 0;
  const tone = !ops ? GRAY : configured.length ? GREEN : ORANGE;

  return (
    <FrostCard
      title="API 池"
      accessory={onOpen ? <GoBtn onClick={onOpen} label="管理" /> : undefined}
    >
      {!ops ? (
        <p className="py-4 text-center text-[12px] text-[var(--console-faint)]">同步中…</p>
      ) : routes.length === 0 && !ops.configured ? (
        <div className="py-4 text-center">
          <p className="text-[12px] text-[#AEAEB2]">尚未配置 API</p>
          {onOpen ? (
            <button
              type="button"
              onClick={onOpen}
              className="mt-2 inline-block text-[11px] font-medium console-status-accent hover:underline"
            >
              前往 {navPathForTab('llm')}
            </button>
          ) : null}
        </div>
      ) : (
        <div className="space-y-2 py-1">
          <div className="flex items-center justify-between text-[11px] text-[var(--console-sub)]">
            <StatusDot
              color={tone}
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
          <ul className="divide-y divide-white/[0.06]">
            {(routes.length ? routes : [{
              id: 'primary',
              name: ops.provider_label || '預設 API',
              model: ops.model,
              allowed_models: ops.allowed_models,
              configured: ops.configured,
              enabled: true,
            }]).slice(0, 4).map((route) => (
              <li key={route.id} className="flex items-center justify-between gap-2 py-1.5 first:pt-0">
                <button
                  type="button"
                  className="min-w-0 truncate text-left text-[12px] font-medium text-[var(--console-ink)] hover:console-status-blue"
                  onClick={onOpen}
                >
                  {route.name}
                </button>
                <span className="shrink-0 font-mono text-[10px] text-[var(--console-sub)]">
                  {route.model || `${route.allowed_models.length} 模`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </FrostCard>
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
    <FrostCard
      title="外部整合"
      accessory={
        onOpenTab ? (
          <GoBtn onClick={() => onOpenTab('integrations')} label="面板" />
        ) : (
          <a href="#/monitor/integrations" className="text-[10px] font-bold console-status-accent hover:underline">
            面板
          </a>
        )
      }
      className={dock ? '' : 'lb-span-2'}
    >
      <IntegrationsStrip density={dock ? 'compact' : 'comfortable'} showSummary={false} showGroups={!dock} />
      <p className="mt-2 text-[10px] leading-relaxed text-[var(--console-faint)]">
        MemOS 記憶 · OpenViking 分層上下文 · WeKnora 知識 · Yao 任務板 · Ouroboros 閘門 · OpenPencil 設計。預設關閉，顯式啟用。
      </p>
    </FrostCard>
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
    'rounded-full border border-[var(--console-line)] bg-[var(--console-card)] px-3 py-1.5 text-[11px] font-medium text-[var(--console-ink)] transition-colors hover:border-[color-mix(in_srgb,var(--console-accent)_40%,transparent)] hover:bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)]';

  return (
    <FrostCard
      title="實驗室工具"
      accessory={
        onOpenLab ? (
          <button
            type="button"
            onClick={() => onOpenLab('prompt')}
            className="text-[10px] font-bold console-status-accent hover:underline"
          >
            實驗室
          </button>
        ) : (
          <a href="#/monitor/lab" className="text-[10px] font-bold console-status-accent hover:underline">
            實驗室
          </a>
        )
      }
      className={dock ? '' : 'lb-span-2'}
    >
      <div className="flex flex-wrap gap-2">
        {LAB_INTEGRATION_TABS.map((item) =>
          onOpenLab ? (
            <button
              key={item.key}
              type="button"
              onClick={() => onOpenLab(item.key)}
              className={chipClass}
              title={item.upstream?.name}
            >
              {item.label}
            </button>
          ) : (
            <a
              key={item.key}
              href={item.key === 'prompt' ? '#/monitor/lab' : `#/monitor/lab/${item.key}`}
              className={chipClass}
              title={item.upstream?.name}
            >
              {item.label}
            </a>
          ),
        )}
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-[var(--console-faint)]">
        Firecrawl 爬蟲 · Prompt Optimizer · Archify 架構 · Ponytail 精簡 · stock-quant 策略庫
      </p>
    </FrostCard>
  );
}

function OverviewKpiRow({ feed }: { feed: AnimLiveFeed }) {
  const dashboard = useMonitorStore((s) => s.dashboard);
  const tasks = dashboard?.tasks ?? [];
  const opt = feed.optimization;
  const hitPct = Math.round((opt?.llm_cache.hit_rate ?? 0) * 100);
  const successRate = opt?.system_stats?.success_rate ?? 0;
  const spark = Array.from({ length: 24 }, (_, h) =>
    tasks.filter((t) => new Date(t.created_at * 1000).getHours() === h).length,
  );

  return (
    <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      {[
        { label: '快取命中', value: `${hitPct}%`, accent: true },
        { label: '成功率', value: `${successRate}%` },
        { label: '執行中', value: String(feed.runningTasks) },
        { label: '角色', value: String(feed.agents.length) },
        { label: 'Trace', value: String(opt?.trace.trace_count ?? 0) },
        { label: 'API', value: String(feed.llmOps?.api_routes?.length ?? 0) },
      ].map((kpi) => (
        <KpiSparkCard key={kpi.label} label={kpi.label} value={kpi.value} spark={spark} accent={kpi.accent} />
      ))}
    </div>
  );
}

export default function LiveBoard({
  feed,
  backgroundPhase,
  density = 'page',
  onOpenLab,
  onOpenTab,
  onOpenTraces,
  onOpenAgent,
}: {
  feed: AnimLiveFeed;
  backgroundPhase?: string | null;
  density?: LiveBoardDensity;
} & LiveBoardNav) {
  const dock = density === 'dock';
  const dashboard = useMonitorStore((s) => s.dashboard);
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

  return (
    <div
      className={`lb-board flex min-h-0 flex-col overflow-hidden ${
        dock ? 'rounded-2xl border border-white/[0.08]' : 'flex-1'
      }`}
    >
      <div
        className={`lb-board-scroll min-h-0 flex-1 overflow-y-auto ${
          dock ? consoleLayout.pagePaddingDense : consoleLayout.pagePadding
        }`}
      >
        {!dock && (
          <header className="mb-3 flex items-center justify-between gap-2">
            <p className="text-[11px] text-[var(--console-sub)]">
              控制台總覽 · API → 角色 → 執行 → 外部整合（MemOS／Viking…）→ 審計／計費
            </p>
            <span className="flex items-center gap-2">
              <StatusDot color={feed.live ? GREEN : GRAY} label={feed.live ? 'LIVE' : 'IDLE'} />
              {updated && <span className="apple-data text-[10px] text-[var(--console-faint)]">{updated}</span>}
            </span>
          </header>
        )}

        {dock && (
          <div className="mb-3 flex items-center gap-2">
            <StatusDot color={feed.live ? GREEN : GRAY} label={feed.live ? 'LIVE' : 'IDLE'} />
            {updated && <span className="font-mono text-[10px] text-[var(--console-faint)]">{updated}</span>}
          </div>
        )}

        {!dock && <WorkflowStrip feed={consoleFeed} onOpenTab={onOpenTab} />}
        {!dock && <OverviewKpiRow feed={consoleFeed} />}
        {!dock && statusStack.length > 0 ? (
          <div className="mb-3 rounded-xl border border-[var(--console-line)] bg-[var(--console-card)] px-3 py-2">
            <p className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-[var(--console-faint)]">任務狀態比例</p>
            <StackBar segments={statusStack} />
          </div>
        ) : null}

        {dock ? (
          <div className="lb-dock-grid">
            <ApiPoolCard feed={feed} onOpen={() => onOpenTab?.('llm')} />
            <CompanyCard
              feed={consoleFeed}
              dock
              onOpen={() => onOpenTab?.('agents')}
              onOpenAgent={onOpenAgent}
              onOpenTab={onOpenTab}
            />
            <div className="lb-span-2">
              <PipelineCard
                feed={feed}
                backgroundPhase={backgroundPhase}
                dock
                onOpen={() => onOpenTab?.('pipeline')}
              />
            </div>
            <BudgetCard feed={feed} dock onOpen={() => onOpenTab?.('models')} />
            <SystemMetricsCard feed={feed} onOpen={() => onOpenTab?.('metrics')} />
            <div className="lb-span-2">
              <EventsCard feed={consoleFeed} dock onOpen={onOpenTraces} />
            </div>
            <div className="lb-span-2">
              <ExternalIntegrationsCard dock onOpenTab={onOpenTab} />
            </div>
            <div className="lb-span-2">
              <LabToolsCard dock onOpenLab={onOpenLab} />
            </div>
          </div>
        ) : (
          <div className="lb-board-grid">
            <ApiPoolCard feed={feed} onOpen={() => onOpenTab?.('llm')} />
            <CompanyCard
              feed={consoleFeed}
              onOpen={() => onOpenTab?.('agents')}
              onOpenAgent={onOpenAgent}
              onOpenTab={onOpenTab}
            />
            <div className="lb-span-2">
              <PipelineCard
                feed={feed}
                backgroundPhase={backgroundPhase}
                onOpen={() => onOpenTab?.('pipeline')}
              />
            </div>
            <BudgetCard feed={feed} onOpen={() => onOpenTab?.('models')} />
            <SystemMetricsCard feed={feed} onOpen={() => onOpenTab?.('metrics')} />
            <div className="lb-span-2">
              <FrostCard title="任務分佈矩陣">
                <TaskDistributionMatrix matrix={taskMatrix} demo={taskMatrix.every((r) => r.every((c) => c.count === 0))} />
              </FrostCard>
            </div>
            <div className="lb-span-2">
              <EventsCard feed={consoleFeed} onOpen={onOpenTraces} />
            </div>
            <ExternalIntegrationsCard onOpenTab={onOpenTab} />
            <LabToolsCard onOpenLab={onOpenLab} />
          </div>
        )}
      </div>
    </div>
  );
}
