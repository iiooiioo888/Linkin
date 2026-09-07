/**
 * LiveBoard — 大螢幕即時監控（Apple 控制中心風格）。
 * 單一柵格、真實狀態驅動；無 KPI 重複列、無場景輪播。
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
  stageBackends,
} from '../lib/animLive';
import { LAB_INTEGRATION_TABS, type LabSubTab } from '../lib/labTabs';

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

function PipelineCard({ feed, dock }: { feed: AnimLiveFeed; dock?: boolean }) {
  const liveIdx =
    mapPhaseToPipelineIndex(feed.streamPhase) ?? mapPhaseToPipelineIndex(feed.taskPhase);
  const phase = feed.streamPhase || feed.taskPhase;

  return (
    <FrostCard
      title="管線"
      accessory={
        <StatusDot color={liveIdx != null ? BLUE : GRAY} label={phase ? String(phase) : '待命'} />
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

function CompanyCard({ feed, dock }: { feed: AnimLiveFeed; dock?: boolean }) {
  const busy = useMemo(() => pickBusyAgents(feed.agents, dock ? 4 : 5), [feed.agents, dock]);
  const active = useMemo(() => pickActiveAgents(feed.agents, 6), [feed.agents]);

  return (
    <FrostCard
      title="協作"
      accessory={
        <StatusDot
          color={active.length ? GREEN : busy.length ? ORANGE : GRAY}
          label={active.length ? `${active.length} 執行` : busy.length ? `${busy.length} 佇列` : '空閒'}
        />
      }
      className={dock ? 'max-h-[180px]' : 'max-h-[240px]'}
      scroll={busy.length > (dock ? 3 : 4)}
    >
      {busy.length === 0 ? (
        <p className="py-6 text-center text-[12px] text-[#636366]">無忙碌角色</p>
      ) : (
        <div className="space-y-4">
          {busy.map((a) => {
            const hot = active.some((x) => x.id === a.id);
            const pct = Math.min(
              100,
              Math.round((a.capacity_used ?? 0) * 100) || (a.executing ? 55 : a.queue ? 20 : 8),
            );
            return (
              <div key={a.id} className="flex items-center gap-3">
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

function BudgetCard({ feed, dock }: { feed: AnimLiveFeed; dock?: boolean }) {
  const b = budgetPct(feed.summary);

  return (
    <FrostCard
      title="預算"
      accessory={
        <StatusDot
          color={b.totalUsd > 0 ? BLUE : GRAY}
          label={b.totalUsd > 0 ? `$${b.totalUsd.toFixed(3)}` : '無用量'}
        />
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

function SystemMetricsCard({ feed }: { feed: AnimLiveFeed }) {
  const opt = feed.optimization;
  const hitPct = Math.round((opt?.llm_cache.hit_rate ?? 0) * 100);
  const traceCount = opt?.trace.trace_count ?? 0;
  const successRate = opt?.system_stats?.success_rate ?? 0;
  const satisfaction = Math.round((opt?.user_feedback?.satisfaction_rate ?? 0) * 100);
  const tone = hitPct >= 30 || traceCount > 0 ? GREEN : GRAY;

  return (
    <FrostCard
      title="系統指標"
      accessory={<StatusDot color={tone} label={hitPct >= 30 ? '快取活躍' : '累積中'} />}
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

function RouterCard({ feed, dock }: { feed: AnimLiveFeed; dock?: boolean }) {
  const backends = useMemo(() => stageBackends(feed.optimization), [feed.optimization]);
  const routing = feed.optimization?.routing_feedback;
  const phase = (feed.streamPhase || feed.taskPhase || '').toLowerCase();
  const hotIdx = backends.findIndex(
    (b) => phase.includes(b.id.toLowerCase()) || phase.includes(b.label.toLowerCase()),
  );
  const maxW = Math.max(...backends.map((b) => b.weight), 1);

  return (
    <FrostCard
      title="路由"
      accessory={
        <StatusDot
          color={hotIdx >= 0 ? BLUE : GRAY}
          label={routing?.total ? `${routing.total}` : `${backends.length}`}
        />
      }
      bodyClassName="apple-chart"
    >
      <div className={`flex items-end gap-3 ${dock ? 'h-[88px]' : 'h-[120px]'} sm:gap-4`}>
        {backends.map((b, i) => {
          const hot = i === hotIdx;
          const h = (dock ? 18 : 24) + (b.weight / maxW) * (dock ? 52 : 76);
          return (
            <div key={b.id} className="flex min-w-0 flex-1 flex-col items-center justify-end">
              <div
                className="w-full rounded-t-lg transition-[height,background] duration-400"
                style={{
                  height: h,
                  background: hot
                    ? `linear-gradient(180deg, ${BLUE}, ${BLUE}88)`
                    : 'rgba(255,255,255,0.08)',
                  boxShadow: hot ? `0 0 16px ${BLUE}44` : undefined,
                }}
              />
              <p
                className="mt-2 truncate text-[10px] font-medium"
                style={{ color: hot ? BLUE : '#AEAEB2' }}
              >
                {b.label}
              </p>
            </div>
          );
        })}
      </div>
    </FrostCard>
  );
}

function EventsCard({ feed, dock }: { feed: AnimLiveFeed; dock?: boolean }) {
  const lines = useMemo(() => buildReportLines(feed.agents, dock ? 4 : 6), [feed.agents, dock]);

  return (
    <FrostCard
      title="事件"
      accessory={
        <StatusDot color={lines.length ? GREEN : GRAY} label={lines.length ? `${lines.length}` : '無'} />
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

function ApiPoolCard({ feed }: { feed: AnimLiveFeed }) {
  const ops = feed.llmOps;
  const routes = ops?.api_routes ?? [];
  const configured = routes.filter((r) => r.configured && r.enabled);
  const strategy = ops?.route_strategy || 'role_preferred';
  const modelCount = ops?.allowed_models.length ?? 0;
  const tone = !ops ? GRAY : configured.length ? GREEN : ORANGE;

  return (
    <FrostCard
      title="API 池"
      accessory={
        <a href="#/monitor/llm" className="text-[10px] font-bold text-[#0A84FF] hover:underline">
          管理
        </a>
      }
    >
      {!ops ? (
        <p className="py-4 text-center text-[12px] text-[#636366]">同步中…</p>
      ) : routes.length === 0 && !ops.configured ? (
        <div className="py-4 text-center">
          <p className="text-[12px] text-[#AEAEB2]">尚未配置 API</p>
          <a
            href="#/monitor/llm"
            className="mt-2 inline-block text-[11px] font-medium text-[#0A84FF] hover:underline"
          >
            前往系統 → API 路由
          </a>
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
                <span className="truncate text-[12px] font-medium text-[#F5F5F7]">{route.name}</span>
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
        Firecrawl 爬蟲 · Prompt Optimizer · Archify 架構 · Ponytail 精簡
      </p>
    </FrostCard>
  );
}

export default function LiveBoard({
  feed,
  density = 'page',
  onOpenLab,
}: {
  feed: AnimLiveFeed;
  density?: LiveBoardDensity;
  onOpenLab?: (sub: LabSubTab) => void;
}) {
  const dock = density === 'dock';
  const updated = feed.updatedAt
    ? new Date(feed.updatedAt).toLocaleTimeString('zh-TW', {
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
          <header className="mb-4 flex items-center justify-end gap-2">
            <StatusDot color={feed.live ? GREEN : GRAY} label={feed.live ? 'LIVE' : 'IDLE'} />
            {updated && <span className="apple-data text-[10px] text-[#636366]">{updated}</span>}
          </header>
        )}

        {dock && (
          <div className="mb-3 flex items-center gap-2">
            <StatusDot color={feed.live ? GREEN : GRAY} label={feed.live ? 'LIVE' : 'IDLE'} />
            {updated && <span className="font-mono text-[10px] text-[#636366]">{updated}</span>}
          </div>
        )}

        {dock ? (
          <div className="lb-dock-grid">
            <div className="lb-span-2">
              <PipelineCard feed={feed} dock />
            </div>
            <CompanyCard feed={feed} dock />
            <BudgetCard feed={feed} dock />
            <ApiPoolCard feed={feed} />
            <div className="lb-span-2">
              <RouterCard feed={feed} dock />
            </div>
            <div className="lb-span-2">
              <EventsCard feed={feed} dock />
            </div>
            <div className="lb-span-2">
              <LabToolsCard dock onOpenLab={onOpenLab} />
            </div>
          </div>
        ) : (
          <div className="lb-board-grid">
            <div className="lb-span-2">
              <PipelineCard feed={feed} />
            </div>
            <CompanyCard feed={feed} />
            <BudgetCard feed={feed} />
            <ApiPoolCard feed={feed} />
            <SystemMetricsCard feed={feed} />
            <div className="lb-span-2">
              <EventsCard feed={feed} />
            </div>
            <LabToolsCard onOpenLab={onOpenLab} />
          </div>
        )}
      </div>
    </div>
  );
}
