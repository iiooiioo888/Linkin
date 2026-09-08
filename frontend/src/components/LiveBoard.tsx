/**
 * LiveBoard — 控制台總覽（Apple 控制中心風格）。
 * 卡片可跳到對應分頁：API 路由／角色／任務／觀測，避免功能孤立。
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
import { filterAgentsByDesk, requestRoleSettingsDesk } from '../lib/agentUi';
import { navPathForTab } from '../lib/monitorTabs';
import type { MonitorTab } from './AppShell';

const PIPELINE = [
  { id: 'sense', label: '感知' },
  { id: 'route', label: '路由' },
  { id: 'gen', label: '生成' },
  { id: 'eval', label: '評估' },
  { id: 'reflect', label: '反思' },
  { id: 'out', label: '輸出' },
];

const BLUE = '#0A84FF';
const GREEN = '#30D158';
const ORANGE = '#FF9F0A';
const RED = '#FF453A';
const GRAY = '#98989D';

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
      className="text-[10px] font-bold text-[#0A84FF] hover:underline"
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
      label: '觀測用量',
      hint: '延遲與成本',
      tab: 'models',
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
                ? 'border-[#0A84FF]/50 bg-[#0A84FF]/10'
                : s.done
                  ? 'border-white/[0.08] bg-[#1C1C1E]'
                  : 'border-white/[0.08] bg-[#1C1C1E] hover:border-[#0A84FF]/40'
            }`}
          >
            <p
              className={`text-[10px] font-bold uppercase tracking-wider ${
                next ? 'text-[#64D2FF]' : s.done ? 'text-[#30D158]' : 'text-[#636366]'
              }`}
            >
              {s.done ? '完成' : next ? '下一步' : s.n}
            </p>
            <p className="mt-0.5 text-[13px] font-semibold text-[#F5F5F7]">{s.label}</p>
            <p className="text-[10px] text-[#8E8E93]">{s.hint}</p>
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
    <span className="inline-flex items-center gap-1.5 text-[10px] text-[#98989D]">
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
      <p className="text-[12px] font-bold text-[#F5F5F7]">{label}</p>
      {sub && <p className="apple-data text-[10px] text-[#8E8E93]">{sub}</p>}
    </div>
  );
}

function PipelineCard({
  feed,
  dock,
  onOpen,
}: {
  feed: AnimLiveFeed;
  dock?: boolean;
  onOpen?: () => void;
}) {
  const liveIdx =
    mapPhaseToPipelineIndex(feed.streamPhase) ?? mapPhaseToPipelineIndex(feed.taskPhase);
  const phase = feed.streamPhase || feed.taskPhase;

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
      <div className={`flex items-center gap-1 ${dock ? 'py-1' : 'py-3'} sm:gap-2`}>
        {PIPELINE.map((n, i) => {
          const active = liveIdx != null && i === liveIdx;
          const done = liveIdx != null && i < liveIdx;
          return (
            <div key={n.id} className="relative flex min-w-0 flex-1 flex-col items-center">
              {i < PIPELINE.length - 1 && (
                <div
                  className={`absolute left-[52%] ${dock ? 'top-[11px]' : 'top-[13px]'} h-[2px] w-[96%]`}
                  style={{ background: done ? GREEN : 'rgba(255,255,255,0.1)' }}
                />
              )}
              <div
                className={`relative z-[1] flex items-center justify-center rounded-full ${
                  dock ? 'h-6 w-6' : 'h-7 w-7'
                }`}
                style={{
                  background: active ? BLUE : done ? `${GREEN}33` : 'rgba(255,255,255,0.06)',
                  boxShadow: active ? `0 0 0 3px ${BLUE}33` : undefined,
                }}
              >
                <span
                  className="text-[9px] font-semibold"
                  style={{ color: active ? '#fff' : done ? GREEN : GRAY }}
                >
                  {i + 1}
                </span>
              </div>
              <span
                className={`mt-2 font-medium ${dock ? 'text-[9px]' : 'text-[10px]'}`}
                style={{ color: active ? '#fff' : '#8E8E93' }}
              >
                {n.label}
              </span>
            </div>
          );
        })}
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
          {onOpen ? <GoBtn onClick={onOpen} label="角色" /> : null}
          {onOpenTab ? <GoBtn onClick={() => onOpenTab('grill')} label="質詢樹" /> : null}
          {onOpenTab ? <GoBtn onClick={() => onOpenTab('memory')} label="L0" /> : null}
        </span>
      }
      className={dock ? 'max-h-[180px]' : 'max-h-[240px]'}
      scroll={busy.length > (dock ? 3 : 4)}
    >
      {busy.length === 0 ? (
        <div className="py-4 text-center">
          <p className="text-[12px] text-[#636366]">無忙碌角色</p>
          {feed.agents.some((a) => a.preferred_model || a.preferred_provider) ? (
            <p className="mt-1 text-[11px] text-[#8E8E93]">
              {feed.agents.filter((a) => a.preferred_model || a.preferred_provider).length} 席已指定模型
            </p>
          ) : onOpen ? (
            <button
              type="button"
              onClick={() => {
                requestRoleSettingsDesk();
                onOpen();
              }}
              className="mt-2 text-[11px] font-medium text-[#0A84FF] hover:underline"
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
                    <p className="truncate text-[12px] font-bold text-[#F5F5F7]">{a.name}</p>
                    <span className="apple-data shrink-0 text-[10px] text-[#8E8E93]">{pct}%</span>
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
      <div className="grid grid-cols-3 gap-4 py-2">
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
        <p className="mt-1 text-center text-[10px] text-[#98989D]">滿意度 {satisfaction}%</p>
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
        <p className="py-8 text-center text-[12px] text-[#636366]">等待事件</p>
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
                <p className="mt-0.5 text-[12px] font-normal leading-snug text-[#F5F5F7]">{s.line}</p>
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
        <p className="py-4 text-center text-[12px] text-[#636366]">同步中…</p>
      ) : routes.length === 0 && !ops.configured ? (
        <div className="py-4 text-center">
          <p className="text-[12px] text-[#AEAEB2]">尚未配置 API</p>
          {onOpen ? (
            <button
              type="button"
              onClick={onOpen}
              className="mt-2 inline-block text-[11px] font-medium text-[#0A84FF] hover:underline"
            >
              前往 {navPathForTab('llm')}
            </button>
          ) : null}
        </div>
      ) : (
        <div className="space-y-2 py-1">
          <div className="flex items-center justify-between text-[11px] text-[#8E8E93]">
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
                  className="min-w-0 truncate text-left text-[12px] font-medium text-[#F5F5F7] hover:text-[#64D2FF]"
                  onClick={onOpen}
                >
                  {route.name}
                </button>
                <span className="shrink-0 font-mono text-[10px] text-[#8E8E93]">
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

function LabToolsCard({
  dock,
  onOpenLab,
}: {
  dock?: boolean;
  onOpenLab?: (sub: LabSubTab) => void;
}) {
  const chipClass =
    'rounded-full border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-[11px] font-medium text-[#F5F5F7] transition-colors hover:border-[#0A84FF]/40 hover:bg-[#0A84FF]/10';

  return (
    <FrostCard
      title="整合工具"
      accessory={
        onOpenLab ? (
          <button
            type="button"
            onClick={() => onOpenLab('prompt')}
            className="text-[10px] font-bold text-[#0A84FF] hover:underline"
          >
            實驗室
          </button>
        ) : (
          <a href="#/monitor/lab" className="text-[10px] font-bold text-[#0A84FF] hover:underline">
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
      <p className="mt-2 text-[10px] leading-relaxed text-[#636366]">
        Firecrawl 爬蟲 · Prompt Optimizer · Archify 架構 · Ponytail 精簡 · stock-quant 策略庫
      </p>
    </FrostCard>
  );
}

export default function LiveBoard({
  feed,
  density = 'page',
  onOpenLab,
  onOpenTab,
  onOpenTraces,
  onOpenAgent,
}: {
  feed: AnimLiveFeed;
  density?: LiveBoardDensity;
} & LiveBoardNav) {
  const dock = density === 'dock';
  const consoleFeed = useMemo(
    () => ({ ...feed, agents: filterAgentsByDesk(feed.agents, 'console') }),
    [feed],
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
          dock ? 'px-3 py-3' : 'px-4 py-4 sm:px-6 sm:py-5'
        }`}
      >
        {!dock && (
          <header className="mb-3 flex items-center justify-between gap-2">
            <p className="text-[11px] text-[#8E8E93]">控制台總覽 · 配置 API → 指定角色 → 執行 → 觀測</p>
            <span className="flex items-center gap-2">
              <StatusDot color={feed.live ? GREEN : GRAY} label={feed.live ? 'LIVE' : 'IDLE'} />
              {updated && <span className="apple-data text-[10px] text-[#636366]">{updated}</span>}
            </span>
          </header>
        )}

        {dock && (
          <div className="mb-3 flex items-center gap-2">
            <StatusDot color={feed.live ? GREEN : GRAY} label={feed.live ? 'LIVE' : 'IDLE'} />
            {updated && <span className="font-mono text-[10px] text-[#636366]">{updated}</span>}
          </div>
        )}

        {!dock && <WorkflowStrip feed={consoleFeed} onOpenTab={onOpenTab} />}

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
              <PipelineCard feed={feed} dock onOpen={() => onOpenTab?.('pipeline')} />
            </div>
            <BudgetCard feed={feed} dock onOpen={() => onOpenTab?.('models')} />
            <SystemMetricsCard feed={feed} onOpen={() => onOpenTab?.('metrics')} />
            <div className="lb-span-2">
              <EventsCard feed={consoleFeed} dock onOpen={onOpenTraces} />
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
              <PipelineCard feed={feed} onOpen={() => onOpenTab?.('pipeline')} />
            </div>
            <BudgetCard feed={feed} onOpen={() => onOpenTab?.('models')} />
            <SystemMetricsCard feed={feed} onOpen={() => onOpenTab?.('metrics')} />
            <div className="lb-span-2">
              <EventsCard feed={consoleFeed} onOpen={onOpenTraces} />
            </div>
            <LabToolsCard onOpenLab={onOpenLab} />
          </div>
        )}
      </div>
    </div>
  );
}
