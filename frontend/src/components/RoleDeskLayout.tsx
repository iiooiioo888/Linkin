/**
 * 角色工作台骨架：標題列、指標帶、右側資訊欄。
 * 色彩沿用控制台既有語彙，只改結構。
 */
import type { ReactNode } from 'react';
import type { AgentEvent, AgentWorkItem, RoleAgent } from '../types';
import { blankMetrics, fmtUsd, fmtWhen } from '../lib/agentUi';
import { EVENT_LABELS, roleLabel } from './TaskPanel';

const RING = 2 * Math.PI * 15.5;

export function roleInitials(name: string): string {
  const latin = name.match(/[A-Za-z0-9]+/g);
  if (latin && latin.join('').length >= 2) return latin.join('').slice(0, 2).toUpperCase();
  return name.slice(0, 2);
}

function pctBar(value: number, max: number): number {
  if (max <= 0) return 0;
  return Math.max(0, Math.min(100, (value / max) * 100));
}

function eventLabel(event: string): string {
  return EVENT_LABELS[event] ?? event.replace(/_/g, ' ');
}

export type RoleDeskTab = 'tasks' | 'monitor' | 'settings';

export function RoleDeskHeader({
  agent,
  modelLabel,
  deskTab,
  onDeskTab,
  extra,
}: {
  agent: RoleAgent;
  modelLabel?: string;
  deskTab: RoleDeskTab;
  onDeskTab: (tab: RoleDeskTab) => void;
  extra?: ReactNode;
}) {
  const open = agent.executing + agent.queue;
  return (
    <div className="rd-header">
      <div className="rd-id">
        <div className="rd-av">{roleInitials(agent.name)}</div>
        <div className="min-w-0">
          <h1 className="rd-name">{agent.name}</h1>
          <div className="rd-tags">
            <span className="rd-tag">L{agent.level} {agent.level_label}</span>
            <span className="rd-tag rd-tag--ok">序列 {agent.queue}</span>
            <span className="rd-tag rd-tag--ok">執行 {agent.executing}</span>
            {agent.max_output_tokens ? (
              <span className="rd-tag rd-tag--muted">推算 {agent.max_output_tokens.toLocaleString()} tok</span>
            ) : null}
            {modelLabel ? <span className="rd-tag rd-tag--muted">{modelLabel}</span> : null}
            {agent.on_call ? <span className="rd-tag">值班</span> : null}
            {agent.enabled === false ? <span className="rd-tag rd-tag--err">停用</span> : null}
          </div>
        </div>
      </div>
      <div className="rd-acts">
        {extra}
        <button
          type="button"
          className={`rd-btn ${deskTab === 'monitor' ? 'on' : ''}`}
          onClick={() => onDeskTab('monitor')}
        >
          監控
        </button>
        <button
          type="button"
          className={`rd-btn ${deskTab === 'settings' ? 'on' : ''}`}
          onClick={() => onDeskTab('settings')}
        >
          設定
        </button>
        <button
          type="button"
          className={`rd-btn ${deskTab === 'tasks' ? 'rd-btn-p' : ''}`}
          onClick={() => onDeskTab('tasks')}
        >
          任用{open > 0 ? ` ${open}` : ''}
        </button>
      </div>
    </div>
  );
}

export function RoleStatsStrip({ agent }: { agent: RoleAgent }) {
  const m = agent.metrics ?? blankMetrics();
  const success = m.success_rate ?? 0;
  const cap = `${agent.capacity_used ?? agent.executing}/${agent.max_parallel_work}`;
  const capPct = m.capacity_pct ?? 0;
  return (
    <div className="rd-stats">
      <div className="rd-stat">
        <span className="rd-stat-l">延遲</span>
        <span className="rd-stat-v">{Math.round(m.avg_latency_ms ?? 0)} ms</span>
      </div>
      <div className="rd-stat">
        <span className="rd-stat-l">P95</span>
        <span className="rd-stat-v">{Math.round(m.p95_latency_ms ?? 0)} ms</span>
      </div>
      <div className="rd-stat">
        <span className="rd-stat-l">成功率</span>
        <span className={`rd-stat-v ${success > 0 ? 'ok' : ''}`}>{success > 0 ? `${success}%` : '—'}</span>
      </div>
      <div className="rd-stat">
        <span className="rd-stat-l">容量</span>
        <span className={`rd-stat-v ${capPct >= 80 ? 'wn' : ''}`}>{cap}</span>
      </div>
      <div className="rd-stat">
        <span className="rd-stat-l">Token I/O</span>
        <span className="rd-stat-v">{m.tokens_in ?? 0} / {m.tokens_out ?? 0}</span>
      </div>
      <div className="rd-stat">
        <span className="rd-stat-l">SLA</span>
        <span className={`rd-stat-v ${(m.sla_breaches ?? 0) > 0 ? 'er' : ''}`}>{m.sla_breaches ?? 0}</span>
      </div>
    </div>
  );
}

function isLive(agent: RoleAgent): boolean {
  return agent.status === 'busy' || agent.status === 'waiting';
}

function OrgNode({
  agent,
  current,
  onOpen,
}: {
  agent: RoleAgent;
  current?: boolean;
  onOpen: (id: string) => void;
}) {
  return (
    <button
      type="button"
      className={`rd-onode ${current ? 'cur' : ''}`}
      title={agent.name}
      onClick={() => onOpen(agent.id)}
    >
      <span className={`rd-od ${isLive(agent) ? 'on' : 'off'}`} />
      <span className="rd-onode-name">{agent.name}</span>
      {current ? <small>本角色</small> : null}
    </button>
  );
}

function resolveByIds(ids: string[] | undefined, byId: Map<string, RoleAgent>): RoleAgent[] {
  const seen = new Set<string>();
  const out: RoleAgent[] = [];
  for (const id of ids ?? []) {
    const next = byId.get(id);
    if (!next || seen.has(next.id)) continue;
    seen.add(next.id);
    out.push(next);
  }
  return out;
}

function preferLive(agents: RoleAgent[]): RoleAgent[] {
  return [...agents].sort((a, b) => Number(isLive(b)) - Number(isLive(a)));
}

function ancestorChain(agent: RoleAgent, byId: Map<string, RoleAgent>): RoleAgent[] {
  const chain: RoleAgent[] = [];
  const seen = new Set<string>([agent.id]);
  let cursor: RoleAgent | undefined = agent;
  while (cursor?.reporting_to) {
    const parent = byId.get(cursor.reporting_to);
    if (!parent || seen.has(parent.id)) break;
    seen.add(parent.id);
    chain.unshift(parent);
    cursor = parent;
  }
  return chain;
}

const MAX_REPORTS = 6;
const MAX_GRAND = 5;
const FORK_W = 320;
const FORK_H = 18;

type OrgLayer = { level: number; nodes: RoleAgent[]; extra: number };

function orgLayers(agent: RoleAgent, agents: RoleAgent[]): OrgLayer[] {
  const byId = new Map(agents.map((item) => [item.id, item]));
  const layers: OrgLayer[] = [
    ...ancestorChain(agent, byId).map((node) => ({ level: node.level, nodes: [node], extra: 0 })),
    { level: agent.level, nodes: [agent], extra: 0 },
  ];
  const reports = preferLive(resolveByIds(agent.direct_reports, byId).filter((item) => item.id !== agent.id));
  if (!reports.length) return layers;

  const shown = reports.slice(0, MAX_REPORTS);
  layers.push({
    level: shown[0].level,
    nodes: shown,
    extra: Math.max(0, reports.length - shown.length),
  });

  const grandchildren = preferLive(
    resolveByIds(
      shown.flatMap((item) => item.direct_reports ?? []),
      byId,
    ).filter((item) => item.id !== agent.id && !shown.some((node) => node.id === item.id)),
  );
  if (!grandchildren.length) return layers;
  const grandShown = grandchildren.slice(0, MAX_GRAND);
  layers.push({
    level: grandShown[0].level,
    nodes: grandShown,
    extra: Math.max(0, grandchildren.length - grandShown.length),
  });
  return layers;
}

function OrgFork({ count }: { count: number }) {
  const ticks = Math.max(1, Math.min(count, 6));
  const mid = FORK_W / 2;
  const pad = ticks === 1 ? mid : 40;
  const span = FORK_W - pad * 2;
  const xs = Array.from({ length: ticks }, (_, i) =>
    ticks === 1 ? mid : pad + (span * i) / (ticks - 1),
  );
  return (
    <div className="rd-tree-conn" aria-hidden>
        <svg viewBox={`0 0 ${FORK_W} ${FORK_H}`} preserveAspectRatio="xMidYMid meet">
        <line x1={mid} y1={0} x2={mid} y2={FORK_H / 2} />
        {ticks > 1 ? (
          <line x1={xs[0]} y1={FORK_H / 2} x2={xs[ticks - 1]} y2={FORK_H / 2} />
        ) : null}
        {xs.map((x, i) => (
          <g key={`tick-${i}`}>
            {ticks > 1 ? <circle cx={x} cy={FORK_H / 2} r={2.5} /> : null}
            <line x1={x} y1={FORK_H / 2} x2={x} y2={FORK_H} />
          </g>
        ))}
      </svg>
    </div>
  );
}

export function OrgReportTree({
  agent,
  agents,
  onOpen,
}: {
  agent: RoleAgent;
  agents: RoleAgent[];
  onOpen: (id: string) => void;
}) {
  const layers = orgLayers(agent, agents);
  const canDelegate = agent.can_delegate_to ?? [];
  const rawReports = (agent.direct_reports ?? []).length;
  const shownIds = new Set(layers.flatMap((layer) => layer.nodes.map((node) => node.id)));
  const unresolvedReports = (agent.direct_reports ?? []).filter(
    (id) => id !== agent.id && !shownIds.has(id) && !agents.some((item) => item.id === id),
  ).length;
  const hasChain = layers.length > 1;

  if (!hasChain) {
    return (
      <div className="rd-sec">
        <div className="rd-tt">組織回報鏈</div>
        <p className="text-[11px] text-[#636366]">
          {rawReports > 0 ? '下級不在此名冊' : '無上級，亦無直屬下級'}
        </p>
        {canDelegate.length > 0 ? (
          <p className="mt-2 text-[10px] text-[#636366]">
            可委派 {canDelegate.slice(0, 4).map(roleLabel).join('、')}
            {canDelegate.length > 4 ? ` 等 ${canDelegate.length}` : ''}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="rd-sec">
      <div className="rd-tt">組織回報鏈</div>
      <div className="rd-tree">
        {layers.map((layer, idx) => (
          <div key={`L${layer.level}-${layer.nodes.map((node) => node.id).join('-')}`} className="rd-tree-block">
            {idx > 0 ? <OrgFork count={layer.nodes.length} /> : null}
            <div className="rd-tree-row">
              <span className="rd-tree-lvl">L{layer.level}</span>
              <div className="rd-tree-nodes">
                {layer.nodes.map((node) => (
                  <OrgNode key={node.id} agent={node} current={node.id === agent.id} onOpen={onOpen} />
                ))}
              </div>
            </div>
            {layer.extra > 0 ? <div className="rd-tree-extra">另 {layer.extra} 位</div> : null}
          </div>
        ))}
      </div>
      {unresolvedReports > 0 ? (
        <p className="mt-2 text-[10px] text-[#636366]">另 {unresolvedReports} 位下級不在此名冊</p>
      ) : null}
    </div>
  );
}

export function TaskStatusBlock({
  agent,
  filter,
  onFilter,
  onOpenItem,
}: {
  agent: RoleAgent;
  filter: string;
  onFilter: (key: string) => void;
  onOpenItem?: (item: AgentWorkItem) => void;
}) {
  const running = agent.work_items.filter((i) => i.status === 'executing');
  const queue = agent.work_items.filter((i) => i.status === 'planning' || i.status === 'ready');
  const done = agent.work_items.filter((i) => i.status === 'done');
  const preview =
    filter === 'done' ? done : filter === 'all' ? agent.work_items : running.length ? running : agent.work_items.filter((i) => i.status === 'executing' || i.status === 'planning' || i.status === 'ready' || i.status === 'in_review');
  return (
    <div className="rd-sec">
      <div className="rd-tt">任務狀態</div>
      <div className="rd-sum">
        <button type="button" className={`rd-card ${filter === 'executing' || filter === 'open' ? 'sel' : ''}`} onClick={() => onFilter('executing')}>
          <div className="rd-num" style={{ color: running.length ? 'var(--apple-orange)' : 'var(--apple-tertiary)' }}>{running.length}</div>
          <div className="rd-lbl">執行中</div>
        </button>
        <button type="button" className={`rd-card ${filter === 'queue' ? 'sel' : ''}`} onClick={() => onFilter('queue')}>
          <div className="rd-num" style={{ color: queue.length ? 'var(--apple-label)' : 'var(--apple-tertiary)' }}>{queue.length}</div>
          <div className="rd-lbl">隊列</div>
        </button>
        <button type="button" className={`rd-card ${filter === 'done' ? 'sel' : ''}`} onClick={() => onFilter('done')}>
          <div className="rd-num" style={{ color: done.length ? 'var(--apple-green)' : 'var(--apple-tertiary)' }}>{done.length}</div>
          <div className="rd-lbl">完成</div>
        </button>
      </div>
      <div className="rd-mini">
        {preview.slice(0, 5).map((item) => (
          <button
            key={`${item.task_id}-${item.id}-${item.kind}`}
            type="button"
            className="rd-item"
            onClick={() => onOpenItem?.(item)}
          >
            <span
              className={`rd-sd ${
                item.status === 'executing' ? 'r' : item.status === 'done' ? 'd' : 'q'
              }`}
            />
            <span className="rd-item-name">{item.title}</span>
            <span className="rd-item-right">{fmtUsd(item.cost_usd)}</span>
          </button>
        ))}
        {preview.length === 0 ? <p className="py-2 text-center text-[11px] text-[#636366]">尚無工作項</p> : null}
      </div>
    </div>
  );
}

export function TokenUsageBlock({ agent }: { agent: RoleAgent }) {
  const m = agent.metrics ?? blankMetrics();
  const tin = m.tokens_in ?? 0;
  const tout = m.tokens_out ?? 0;
  const ctx = agent.context_window || agent.max_output_tokens || 4096;
  const used = tin + tout;
  const max = Math.max(ctx, used, 1);
  const inLen = RING * (tin / max);
  const outLen = RING * (tout / max);
  return (
    <div className="rd-sec">
      <div className="rd-tt">Token 用量</div>
      <div className="rd-tk">
        <div className="rd-ring">
          <svg viewBox="0 0 40 40">
            <circle className="rd-ring-bg" cx="20" cy="20" r="15.5" />
            <circle
              cx="20"
              cy="20"
              r="15.5"
              stroke="var(--apple-blue)"
              strokeDasharray={`${inLen} ${RING}`}
              strokeDashoffset={0}
            />
            <circle
              cx="20"
              cy="20"
              r="15.5"
              stroke="var(--apple-green)"
              strokeDasharray={`${outLen} ${RING}`}
              strokeDashoffset={-inLen}
            />
          </svg>
          <div className="rd-center">
            <span className="apple-data text-[15px] font-bold leading-none">{used.toLocaleString()}</span>
            <span className="mt-0.5 text-[7.5px] uppercase tracking-wide text-[#636366]">tok</span>
          </div>
        </div>
        <div className="rd-tk-brk">
          {[
            { label: 'Input', value: tin, color: 'var(--apple-blue)', max: ctx },
            { label: 'Output', value: tout, color: 'var(--apple-green)', max: ctx },
            { label: 'Context', value: ctx, color: '#bf5af2', max: ctx },
          ].map((row) => (
            <div key={row.label}>
              <div className="rd-tk-item">
                <span className="rd-tk-dot" style={{ background: row.color }} />
                <span className="rd-tk-l">{row.label}</span>
                <span className="rd-tk-v">{row.value.toLocaleString()} tok</span>
              </div>
              <div className="rd-tk-bar">
                <div className="rd-bar-f" style={{ width: `${pctBar(row.value, row.max)}%`, background: row.color }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function CostDetailBlock({ agent }: { agent: RoleAgent }) {
  const m = agent.metrics ?? blankMetrics();
  const api = m.api_spent_usd ?? agent.api_cost_usd ?? 0;
  const docker = agent.docker_cost_usd ?? 0;
  const aliyun = agent.aliyun_cost_usd ?? 0;
  const total = m.daily_spent_usd ?? agent.cost_usd ?? api + docker + aliyun;
  const budget = agent.daily_budget_usd ?? 0;
  const scale = Math.max(total, budget, 0.001);
  return (
    <div className="rd-sec">
      <div className="rd-tt">費用明細</div>
      <div className="rd-grid2">
        <div className="rd-cell">
          <div className="rd-cell-l">LLM API</div>
          <div className="rd-cell-v" style={{ color: 'var(--apple-blue-soft)' }}>{fmtUsd(api)}</div>
          <div className="rd-bar"><div className="rd-bar-f" style={{ width: `${pctBar(api, scale)}%`, background: 'var(--apple-blue)' }} /></div>
        </div>
        <div className="rd-cell">
          <div className="rd-cell-l">Docker</div>
          <div className="rd-cell-v">{fmtUsd(docker)}</div>
          <div className="rd-bar"><div className="rd-bar-f" style={{ width: `${pctBar(docker, scale)}%`, background: 'var(--apple-green)' }} /></div>
        </div>
        <div className="rd-cell">
          <div className="rd-cell-l">阿里雲</div>
          <div className="rd-cell-v">{fmtUsd(aliyun)}</div>
          <div className="rd-bar"><div className="rd-bar-f" style={{ width: `${pctBar(aliyun, scale)}%`, background: '#bf5af2' }} /></div>
        </div>
        <div className="rd-cell">
          <div className="rd-cell-l">日預算</div>
          <div className="rd-cell-v">{budget > 0 ? fmtUsd(budget) : '不限'}</div>
        </div>
      </div>
      <div className="rd-cost-tot">
        <span className="rd-cost-tot-l">今日合計</span>
        <span className="rd-cost-tot-v">{fmtUsd(total)}</span>
      </div>
      <div className="rd-cost-note">
        <span>含 API + Docker</span>
        <span>預算告警：{m.budget_alerts ?? 0}</span>
      </div>
    </div>
  );
}

export function RdCell({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="rd-cell">
      <div className="rd-cell-l">{label}</div>
      <div className="rd-cell-v" style={{ fontSize: 14, ...(color ? { color } : {}) }}>
        {value}
      </div>
    </div>
  );
}

export function RoleMonitorBlock({ agent }: { agent: RoleAgent }) {
  const m = agent.metrics ?? blankMetrics();
  const handled = agent.company_tasks?.length ?? 0;
  return (
    <div className="rd-sec">
      <div className="rd-tt">角色監控</div>
      <div className="rd-grid2">
        <div className="rd-cell">
          <div className="rd-cell-l">協辦任務</div>
          <div className="rd-cell-v" style={{ color: 'var(--apple-blue-soft)', fontSize: 14 }}>{handled || agent.work_items.length}</div>
        </div>
        <div className="rd-cell">
          <div className="rd-cell-l">本角色經手</div>
          <div className="rd-cell-v" style={{ color: 'var(--apple-tertiary)', fontSize: 14 }}>{handled ? handled : '—'}</div>
        </div>
        <div className="rd-cell">
          <div className="rd-cell-l">預算告警</div>
          <div className="rd-cell-v" style={{ color: (m.budget_alerts ?? 0) > 0 ? 'var(--apple-orange)' : 'var(--apple-green)', fontSize: 14 }}>
            {m.budget_alerts ?? 0}
          </div>
        </div>
        <div className="rd-cell">
          <div className="rd-cell-l">錯誤</div>
          <div className="rd-cell-v" style={{ color: (m.errors ?? 0) > 0 ? 'var(--apple-red)' : 'var(--apple-green)', fontSize: 14 }}>
            {m.errors ?? 0}
          </div>
        </div>
      </div>
    </div>
  );
}

export function EventTimelineBlock({ events }: { events: AgentEvent[] }) {
  return (
    <div className="rd-sec">
      <div className="rd-tt">事件時間線</div>
      {events.length === 0 ? (
        <p className="py-1 text-[11px] text-[#636366]">尚無此角色事件</p>
      ) : (
        <div className="rd-ev">
          {events.slice(0, 8).map((ev, i) => {
            const bad = ev.event.includes('error') || ev.event.includes('fail');
            return (
              <div key={`${ev.ts}-${ev.event}-${i}`} className="rd-ev-row">
                <span className={`rd-ev-dot ${bad ? 'er' : 'go'}`} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[10.5px] text-[#AEAEB2]">
                    {ev.title ? `${ev.title} — ${eventLabel(ev.event)}` : eventLabel(ev.event)}
                  </div>
                  <div className="apple-data text-[8.5px] text-[#636366]">{fmtWhen(ev.ts)}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function RoleRightPanel({
  agent,
  agents,
  filter,
  onFilter,
  onOpen,
  onOpenItem,
}: {
  agent: RoleAgent;
  agents: RoleAgent[];
  filter: string;
  onFilter: (key: string) => void;
  onOpen: (id: string) => void;
  onOpenItem?: (item: AgentWorkItem) => void;
}) {
  return (
    <aside className="rd-rp">
      <OrgReportTree agent={agent} agents={agents} onOpen={onOpen} />
      <TaskStatusBlock agent={agent} filter={filter} onFilter={onFilter} onOpenItem={onOpenItem} />
      <TokenUsageBlock agent={agent} />
      <CostDetailBlock agent={agent} />
      <RoleMonitorBlock agent={agent} />
      <EventTimelineBlock events={agent.events ?? []} />
    </aside>
  );
}
