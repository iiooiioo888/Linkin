/**
 * LiveBoard 卡片：協作／預算／運行指標／事件／API 池。
 */
import { useMemo } from 'react';
import { requestRoleSettingsDesk } from '../../lib/agentUi';
import { budgetPct, buildReportLines, pickActiveAgents, pickBusyAgents, type AnimLiveFeed } from '../../lib/animLive';
import { navPathForTab } from '../../lib/monitorTabs';
import type { MonitorTab } from '../AppShell';
import {
  KpiSparkCard,
  MiniProgressBar,
  MonitorKpiGrid,
  MonitorLinkButton,
  MonitorPanel,
  MonitorStatusDot,
  ResourceGauges,
} from '../ui/monitor';
import type { MonitorStatusTone } from '../ui/monitor';

export function CompanyCard({
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
          {onOpen ? <MonitorLinkButton onClick={onOpen} label="席位" /> : null}
          {onOpenTab ? <MonitorLinkButton onClick={() => onOpenTab('memory')} label="世界" /> : null}
          {onOpenTab ? <MonitorLinkButton onClick={() => onOpenTab('integrations')} label="整合" /> : null}
        </>
      }
      scroll={busy.length > (dock ? 3 : 4)}
      className={dock ? 'max-h-[180px]' : 'max-h-[240px]'}
    >
      {busy.length === 0 ? (
        <div className="py-4 text-center">
          <p className="text-[12px] text-[var(--console-faint)]">無忙碌席位</p>
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

export function BudgetCard({
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

export function SystemMetricsCard({
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

export function EventsCard({
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

export function ApiPoolCard({ feed, onOpen }: { feed: AnimLiveFeed; onOpen?: () => void }) {
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
