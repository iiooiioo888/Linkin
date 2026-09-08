/**
 * 角色工作台骨架：標題列、指標帶、右側資訊欄。
 * 色彩沿用控制台既有語彙，只改結構。
 */
import { Fragment, useMemo, type ReactNode } from 'react';
import type { AgentEvent, AgentWorkItem, GrillTreeNode, L0Snapshot, RoleAgent } from '../types';
import {
  blankMetrics,
  fmtUsd,
  fmtWhen,
  itemsInColumn,
  workItemColumnKey,
  WORK_ITEM_COLUMN_COLOR,
  WORK_ITEM_COLUMNS,
  type WorkItemColumnKey,
} from '../lib/agentUi';
import { EVENT_LABELS, roleLabel } from './TaskPanel';
import {
  agentRahoLabel,
  jumpLayer,
  jumpToGrillTree,
  jumpToL0Kernel,
  kindLabel,
  nodeRoleLabel,
  orgLevelCaption,
  RAHO_CHAIN,
  RAHO_LAYERS,
  rahoTone,
  statusLabel,
} from '../lib/rahoUi';

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

export type RoleDeskTab = 'tasks' | 'monitor' | 'settings' | 'quant';

export function RoleDeskHeader({
  agent,
  modelLabel,
  deskTab,
  onDeskTab,
  extra,
  showQuant,
}: {
  agent: RoleAgent;
  modelLabel?: string;
  deskTab: RoleDeskTab;
  onDeskTab: (tab: RoleDeskTab) => void;
  extra?: ReactNode;
  showQuant?: boolean;
}) {
  const open = agent.executing + agent.queue;
  return (
    <div className="rd-header">
      <div className="rd-id">
        <div className="rd-av">{roleInitials(agent.name)}</div>
        <div className="min-w-0">
          <h1 className="rd-name">{agent.name}</h1>
          <div className="rd-tags">
            <span className="rd-tag rd-tag--raho">{agentRahoLabel(agent)}</span>
            <span className="rd-tag rd-tag--muted">{orgLevelCaption(agent)}</span>
            <span className="rd-tag rd-tag--ok">序列 {agent.queue}</span>
            <span className="rd-tag rd-tag--ok">執行 {agent.executing}</span>
            {agent.max_output_tokens ? (
              <span className="rd-tag rd-tag--muted">推算 {agent.max_output_tokens.toLocaleString()} tok</span>
            ) : null}
            {modelLabel ? <span className="rd-tag rd-tag--muted">{modelLabel}</span> : null}
            {agent.on_call ? <span className="rd-tag">值班</span> : null}
            {agent.enabled === false ? <span className="rd-tag rd-tag--err">停用</span> : null}
            {agent.demoted || agent.metrics?.demoted ? (
              <span className="rd-tag rd-tag--err">規劃已降級</span>
            ) : agent.raho_rank === 'watch' || agent.metrics?.raho_rank === 'watch' ? (
              <span className="rd-tag">被質詢偏高</span>
            ) : null}
          </div>
        </div>
      </div>
      <div className="rd-acts">
        {extra}
        {showQuant ? (
          <button
            type="button"
            className={`rd-btn ${deskTab === 'quant' ? 'on' : ''}`}
            onClick={() => onDeskTab('quant')}
          >
            策略庫
          </button>
        ) : null}
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
      title={`${agentRahoLabel(agent)} · ${agent.name}`}
      onClick={() => onOpen(agent.id)}
    >
      <span className={`rd-od ${isLive(agent) ? 'on' : 'off'}`} />
      <span className="rd-onode-name">{agent.name}</span>
      {current ? <small>本角色</small> : null}
    </button>
  );
}

function preferLive(agents: RoleAgent[]): RoleAgent[] {
  return [...agents].sort((a, b) => {
    const live = Number(isLive(b)) - Number(isLive(a));
    if (live) return live;
    if (a.level !== b.level) return a.level - b.level;
    return a.name.localeCompare(b.name, 'zh-Hant');
  });
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

function childrenOf(id: string, agents: RoleAgent[], byId: Map<string, RoleAgent>): RoleAgent[] {
  const seen = new Set<string>();
  const out: RoleAgent[] = [];
  const push = (item: RoleAgent | undefined) => {
    if (!item || item.id === id || seen.has(item.id)) return;
    seen.add(item.id);
    out.push(item);
  };
  for (const childId of byId.get(id)?.direct_reports ?? []) push(byId.get(childId));
  for (const item of agents) {
    if (item.reporting_to === id) push(item);
  }
  return preferLive(out);
}

const MAX_PER_LAYER = 8;

type OrgLayer = { key: string; label: string; nodes: RoleAgent[]; extra: number };

function layerLabel(nodes: RoleAgent[]): string {
  const raho = [...new Set(nodes.map((node) => node.raho_layer).filter((n): n is number => typeof n === 'number'))];
  if (raho.length === 1) return RAHO_LAYERS[raho[0]]?.short ?? `L${raho[0]}`;
  const levels = [...new Set(nodes.map((node) => node.level))].sort((a, b) => a - b);
  if (levels.length === 1) return nodes[0]?.level_label || `組織 ${levels[0]}`;
  return `${nodes[0]?.level_label || '組織'} 等`;
}

function takeLayer(key: string, nodes: RoleAgent[]): OrgLayer {
  return {
    key,
    label: layerLabel(nodes),
    nodes: nodes.slice(0, MAX_PER_LAYER),
    extra: Math.max(0, nodes.length - MAX_PER_LAYER),
  };
}

function orgLayers(agent: RoleAgent, agents: RoleAgent[]): OrgLayer[] {
  const byId = new Map(agents.map((item) => [item.id, item]));
  const layers: OrgLayer[] = [
    ...ancestorChain(agent, byId).map((node) => ({
      key: `up-${node.id}`,
      label: node.raho_short || orgLevelCaption(node),
      nodes: [node],
      extra: 0,
    })),
    { key: `cur-${agent.id}`, label: agent.raho_short || orgLevelCaption(agent), nodes: [agent], extra: 0 },
  ];
  const reports = childrenOf(agent.id, agents, byId);
  if (!reports.length) return layers;
  const down = takeLayer(`down-${agent.id}`, reports);
  layers.push(down);

  const seen = new Set([agent.id, ...down.nodes.map((item) => item.id)]);
  const uniqueGrand: RoleAgent[] = [];
  for (const item of preferLive(down.nodes.flatMap((node) => childrenOf(node.id, agents, byId)))) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    uniqueGrand.push(item);
  }
  if (uniqueGrand.length) layers.push(takeLayer(`skip-${agent.id}`, uniqueGrand));
  return layers;
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
  const layers = useMemo(() => orgLayers(agent, agents), [agent, agents]);
  const canDelegate = agent.can_delegate_to ?? [];
  const reportsHere = agents.filter((item) => item.reporting_to === agent.id || (agent.direct_reports ?? []).includes(item.id)).length;
  const missing = (agent.direct_reports ?? []).filter(
    (id) =>
      id !== agent.id &&
      !id.startsWith('custom_linkin_') &&
      !agents.some((item) => item.id === id),
  ).length;

  return (
    <div className="rd-sec">
      <div className="rd-tt">組織回報鏈</div>
      <div className="rd-tree">
        {layers.map((layer, idx) => (
          <Fragment key={layer.key}>
            {idx > 0 ? <div className="rd-tree-conn" aria-hidden /> : null}
            <div className="rd-tree-row">
              <span className="rd-tree-lvl">{layer.label}</span>
              <div className="rd-tree-nodes">
                {layer.nodes.map((node) => (
                  <OrgNode
                    key={node.id}
                    agent={node}
                    current={node.id === agent.id}
                    onOpen={onOpen}
                  />
                ))}
                {layer.extra > 0 ? (
                  <span className="rd-onode rd-onode-more">另 {layer.extra}</span>
                ) : null}
              </div>
            </div>
          </Fragment>
        ))}
      </div>
      {layers.length < 2 ? (
        <p className="mt-2 text-[10px] text-[#636366]">
          {missing > 0 ? '下級不在此名冊' : reportsHere > 0 ? '直屬已列於上方' : '無上級，亦無直屬下級'}
        </p>
      ) : null}
      {missing > 0 ? <p className="mt-2 text-[10px] text-[#636366]">另 {missing} 位下級不在此名冊</p> : null}
      {layers.length < 2 && canDelegate.length > 0 ? (
        <p className="mt-2 text-[10px] text-[#636366]">
          可委派 {canDelegate.slice(0, 4).map(roleLabel).join('、')}
          {canDelegate.length > 4 ? ` 等 ${canDelegate.length}` : ''}
        </p>
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
  filter: WorkItemColumnKey;
  onFilter: (key: WorkItemColumnKey) => void;
  onOpenItem?: (item: AgentWorkItem) => void;
}) {
  const activeKey: WorkItemColumnKey = filter;
  const preview = itemsInColumn(agent.work_items, activeKey);
  return (
    <div className="rd-sec">
      <div className="rd-tt">任務狀態</div>
      <div className="rd-sum">
        {WORK_ITEM_COLUMNS.map((col) => {
          const count = itemsInColumn(agent.work_items, col.key).length;
          return (
            <button
              key={col.key}
              type="button"
              className={`rd-card ${activeKey === col.key ? 'sel' : ''}`}
              onClick={() => onFilter(col.key)}
            >
              <div
                className="rd-num"
                style={{ color: count ? WORK_ITEM_COLUMN_COLOR[col.key] : 'var(--apple-tertiary)' }}
              >
                {count}
              </div>
              <div className="rd-lbl">{col.label}</div>
            </button>
          );
        })}
      </div>
      <div className="rd-mini">
        {preview.slice(0, 5).map((item) => {
          const col = workItemColumnKey(item.status);
          return (
          <button
            key={`${item.task_id}-${item.id}-${item.kind}`}
            type="button"
            className="rd-item"
            onClick={() => onOpenItem?.(item)}
          >
            <span className={`rd-sd ${col === 'executing' ? 'r' : col === 'done' ? 'd' : 'q'}`} />
            <span className="rd-item-name">{item.title}</span>
            <span className="rd-item-right">{fmtUsd(item.cost_usd)}</span>
          </button>
          );
        })}
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
  const cloud = m.cloud_spent_usd ?? agent.cloud_cost_usd ?? docker + aliyun;
  const total = m.daily_spent_usd ?? agent.cost_usd ?? api + cloud;
  const aiDaily = agent.daily_budget_usd ?? 0;
  const aiWeekly = agent.weekly_budget_usd ?? 0;
  const aiMonthly = agent.monthly_budget_usd ?? 0;
  const cloudDaily = agent.cloud_daily_budget_usd ?? 0;
  const cloudWeekly = agent.cloud_weekly_budget_usd ?? 0;
  const cloudMonthly = agent.cloud_monthly_budget_usd ?? 0;
  const aiScale = Math.max(api, aiDaily, 0.001);
  const cloudScale = Math.max(cloud, cloudDaily, docker, aliyun, 0.001);
  const limitLabel = (n: number) => (n > 0 ? fmtUsd(n) : '不限');
  return (
    <div className="rd-sec">
      <div className="rd-tt">費用明細</div>
      <div className="rd-budget-block">
        <div className="rd-budget-h">
          <strong>AI 使用預算</strong>
          <span>只計 LLM API</span>
        </div>
        <div className="rd-grid2">
          <div className="rd-cell">
            <div className="rd-cell-l">今日已用</div>
            <div className="rd-cell-v" style={{ color: agent.ai_budget_over ? 'var(--apple-orange)' : 'var(--apple-blue-soft)' }}>{fmtUsd(api)}</div>
            <div className="rd-bar"><div className="rd-bar-f" style={{ width: `${pctBar(api, aiScale)}%`, background: 'var(--apple-blue)' }} /></div>
          </div>
          <div className="rd-cell">
            <div className="rd-cell-l">日／週／月</div>
            <div className="rd-cell-v">{limitLabel(aiDaily)} / {limitLabel(aiWeekly)} / {limitLabel(aiMonthly)}</div>
          </div>
        </div>
      </div>
      <div className="rd-budget-block">
        <div className="rd-budget-h">
          <strong>雲服務預算</strong>
          <span>Docker＋阿里雲</span>
        </div>
        <div className="rd-grid2">
          <div className="rd-cell">
            <div className="rd-cell-l">Docker</div>
            <div className="rd-cell-v">{fmtUsd(docker)}</div>
            <div className="rd-bar"><div className="rd-bar-f" style={{ width: `${pctBar(docker, cloudScale)}%`, background: 'var(--apple-green)' }} /></div>
          </div>
          <div className="rd-cell">
            <div className="rd-cell-l">阿里雲</div>
            <div className="rd-cell-v">{fmtUsd(aliyun)}</div>
            <div className="rd-bar"><div className="rd-bar-f" style={{ width: `${pctBar(aliyun, cloudScale)}%`, background: '#bf5af2' }} /></div>
          </div>
          <div className="rd-cell">
            <div className="rd-cell-l">雲服務小計</div>
            <div className="rd-cell-v" style={{ color: agent.cloud_budget_over ? 'var(--apple-orange)' : undefined }}>{fmtUsd(cloud)}</div>
          </div>
          <div className="rd-cell">
            <div className="rd-cell-l">日／週／月</div>
            <div className="rd-cell-v">{limitLabel(cloudDaily)} / {limitLabel(cloudWeekly)} / {limitLabel(cloudMonthly)}</div>
          </div>
        </div>
      </div>
      <div className="rd-cost-tot">
        <span className="rd-cost-tot-l">今日合計（參考）</span>
        <span className="rd-cost-tot-v">{fmtUsd(total)}</span>
      </div>
      <div className="rd-cost-note">
        <span>兩筆預算互不混算</span>
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

export function RahoChainBlock({ agent }: { agent: RoleAgent }) {
  const current = agent.raho_layer ?? 2;
  return (
    <div className="rd-sec">
      <div className="rd-tt">
        質詢鏈
        <button type="button" className="rd-link" onClick={jumpToGrillTree}>
          開質詢樹
        </button>
      </div>
      <div className="raho-desk-chain">
        {RAHO_CHAIN.map((layer) => {
          const meta = RAHO_LAYERS[layer];
          const active = layer === current;
          const clickable = Boolean(meta.role_id && meta.role_id !== 'user');
          return (
            <button
              key={layer}
              type="button"
              className={`raho-desk-chip${active ? ' on' : ''}${layer === 0 ? ' is-l0' : ''}`}
              disabled={!clickable}
              onClick={() => clickable && jumpLayer(layer, meta.role_id)}
            >
              {meta.short}
            </button>
          );
        })}
      </div>
      {(agent.grill_targets?.length ?? 0) > 0 ? (
        <p className="mt-2 text-[10px] text-[#636366]">可質詢 {agent.grill_targets!.join('、')}</p>
      ) : null}
    </div>
  );
}

export function GrillFeedBlock({ nodes }: { nodes: GrillTreeNode[] }) {
  return (
    <div className="rd-sec">
      <div className="rd-tt">此角色質詢</div>
      {nodes.length === 0 ? (
        <p className="py-1 text-[11px] text-[#636366]">尚無與此角色相關的質詢</p>
      ) : (
        <div className="rd-ev">
          {nodes.slice(0, 6).map((node) => (
            <button
              key={node.node_id}
              type="button"
              className="rd-ev-row raho-feed-row"
              onClick={jumpToGrillTree}
            >
              <span className="rd-ev-dot" style={{ background: rahoTone(node.status) }} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[10.5px] text-[#AEAEB2]">
                  {nodeRoleLabel(node, 'from')} → {nodeRoleLabel(node, 'to')}
                </div>
                <div className="truncate text-[10px] text-[#EBEBF5]">{node.summary}</div>
                <div className="apple-data text-[8.5px] text-[#636366]">
                  {kindLabel(node.kind_label || node.kind)} · {statusLabel(node.status)}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function L0ContextBlock({ snapshot }: { snapshot?: L0Snapshot | null }) {
  const radar = snapshot?.radar;
  const pressure = Math.round((radar?.pressure ?? 0) * 100);
  const lesson = snapshot?.traces?.find((t) => t.failure_reason) ?? snapshot?.traces?.[0];
  const knowledge = snapshot?.knowledge?.[0];
  return (
    <div className="rd-sec">
      <div className="rd-tt">
        L0 知識與記憶
        <button type="button" className="rd-link" onClick={jumpToL0Kernel}>
          開核心
        </button>
      </div>
      <p className="text-[11px] leading-relaxed text-[#AEAEB2]">
        {radar?.bias_instructions || '環境壓力正常，依規格驗收。'}
      </p>
      <p className={`mt-1 text-[10px] ${radar?.energy_save ? 'text-[#FF9F0A]' : 'text-[#636366]'}`}>
        壓力 {pressure}%{radar?.energy_save ? ' · 節能模式' : ''}
      </p>
      {knowledge ? <p className="mt-1 text-[10px] text-[#8E8E93]">知識：{knowledge.content}</p> : null}
      {lesson ? <p className="mt-1 text-[10px] text-[#8E8E93]">記憶：{lesson.summary}</p> : null}
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
  grillNodes,
  l0,
}: {
  agent: RoleAgent;
  agents: RoleAgent[];
  filter: WorkItemColumnKey;
  onFilter: (key: WorkItemColumnKey) => void;
  onOpen: (id: string) => void;
  onOpenItem?: (item: AgentWorkItem) => void;
  grillNodes?: GrillTreeNode[];
  l0?: L0Snapshot | null;
}) {
  return (
    <aside className="rd-rp">
      <RahoChainBlock agent={agent} />
      <L0ContextBlock snapshot={l0} />
      <GrillFeedBlock nodes={grillNodes ?? []} />
      <OrgReportTree agent={agent} agents={agents} onOpen={onOpen} />
      <TaskStatusBlock agent={agent} filter={filter} onFilter={onFilter} onOpenItem={onOpenItem} />
      <TokenUsageBlock agent={agent} />
      <CostDetailBlock agent={agent} />
      <RoleMonitorBlock agent={agent} />
      <EventTimelineBlock events={agent.events ?? []} />
    </aside>
  );
}
