/**
 * 角色 Agent 監控共用顯示邏輯。
 */
import type { AgentWorkItem, ModelRateCard, ModelRateCatalog, RoleAgent } from '../types';

export const AGENT_STATUS_META: Record<string, { label: string; dot: string; text: string }> = {
  busy: { label: '執行中', dot: 'bg-[#4cc38a] animate-pulse', text: 'text-[#4cc38a]' },
  waiting: { label: '等待中', dot: 'bg-amber-400', text: 'text-amber-300' },
  error: { label: '阻塞', dot: 'bg-red-400', text: 'text-red-300' },
  idle: { label: '待命', dot: 'bg-[#62666d]', text: 'text-[#8a8f98]' },
  disabled: { label: '停用', dot: 'bg-[#3a3d44]', text: 'text-[#62666d]' },
};

export const TIER_LABEL: Record<string, string> = {
  critical: '關鍵模型',
  reasoning: '推理模型',
  routine: '日常模型',
  summary: '摘要模型',
};

export function blankMetrics() {
  return {
    review_pass: 0,
    review_rework: 0,
    review_force: 0,
    errors: 0,
    tool_calls: 0,
    budget_alerts: 0,
    items_total: 0,
    success_rate: 0,
    avg_cost_usd: 0,
    capacity_pct: 0,
    daily_spent_usd: 0,
    api_spent_usd: 0,
    cloud_spent_usd: 0,
    avg_latency_ms: 0,
    tokens_in: 0,
    tokens_out: 0,
    last_model: '',
    sla_breaches: 0,
    retries: 0,
    failovers: 0,
    cache_hits: 0,
    human_escalations: 0,
    p95_latency_ms: 0,
    weekly_spent_usd: 0,
    weekly_cloud_spent_usd: 0,
    grill_count: 0,
    grill_rate: 0,
    decision_clarity: 1,
    demoted: false,
    raho_rank: 'ok',
  };
}

export const ROUTING_LABEL: Record<string, string> = {
  quality_first: '品質優先',
  cost_first: '成本優先',
  speed_first: '速度優先',
  manual: '指定模型',
};

export const CATEGORY_LABEL: Record<string, string> = {
  ui: 'UI 設計',
  css: '樣式',
  js: '前端邏輯',
  backend: '後端',
  test: '測試',
  devops: '維運',
  management: '管理',
  review: '審查',
  security: '資安',
  data: '資料',
  product: '產品',
  docs: '文件',
  mobile: '行動端',
  research: '研究',
  ai: 'AI / Prompt',
  legal: '合規',
  finance: '金融／量化',
  industrial: '工業／OPC',
  creative: '創意／敘事',
  crawler: '爬蟲／採集',
  platform: '平台／GitHub',
  hub: 'AI Hub',
  memory: '記憶／知識庫',
  growth: '成長／客戶成功',
};

export function agentOpenCount(agent: Pick<RoleAgent, 'queue' | 'executing' | 'inbox' | 'blocked'>): number {
  return agent.queue + agent.executing + (agent.inbox.in_review ?? 0) + agent.blocked;
}

/** 控制台任用／任務子項統一三欄：隊列 → 執行中 → 已完成 */
export const WORK_ITEM_COLUMNS = [
  { key: 'queue', label: '隊列', statuses: ['planning', 'ready', 'blocked'] },
  { key: 'executing', label: '執行中', statuses: ['executing', 'in_review', 'rework'] },
  { key: 'done', label: '已完成', statuses: ['done'] },
] as const;

export type WorkItemColumnKey = (typeof WORK_ITEM_COLUMNS)[number]['key'];

export const WORK_ITEM_COLUMN_COLOR: Record<WorkItemColumnKey, string> = {
  queue: 'var(--apple-label)',
  executing: 'var(--apple-orange)',
  done: 'var(--apple-green)',
};

export function workItemColumnKey(status: string): WorkItemColumnKey {
  for (const col of WORK_ITEM_COLUMNS) {
    if ((col.statuses as readonly string[]).includes(status)) return col.key;
  }
  return 'queue';
}

export function itemsInColumn(items: AgentWorkItem[], key: WorkItemColumnKey): AgentWorkItem[] {
  return items.filter((item) => workItemColumnKey(item.status) === key);
}

/** 控制台任務列表同一套三欄：隊列 → 執行中 → 已完成 */
export const TASK_COLUMNS = [
  { key: 'queue', label: '隊列', statuses: ['pending'] },
  { key: 'running', label: '執行中', statuses: ['running'] },
  { key: 'done', label: '已完成', statuses: ['completed', 'failed', 'cancelled', 'interrupted'] },
] as const;

export type TaskColumnKey = (typeof TASK_COLUMNS)[number]['key'];

export function taskColumnKey(status: string): TaskColumnKey {
  for (const col of TASK_COLUMNS) {
    if ((col.statuses as readonly string[]).includes(status)) return col.key;
  }
  return 'queue';
}

export function tasksInColumn<T extends { status: string }>(items: T[], key: TaskColumnKey): T[] {
  return items.filter((item) => taskColumnKey(item.status) === key);
}

/** 管線階段：尚未走到＝隊列，當前＝執行中，已過＝已完成 */
export const PIPELINE_STAGES = [
  { id: 'sense', label: '感知' },
  { id: 'route', label: '路由' },
  { id: 'gen', label: '生成' },
  { id: 'eval', label: '評估' },
  { id: 'reflect', label: '反思' },
  { id: 'out', label: '輸出' },
] as const;

export function pipelineStageColumn(index: number, activeIndex: number | null): WorkItemColumnKey {
  if (activeIndex == null) return 'queue';
  if (index < activeIndex) return 'done';
  if (index === activeIndex) return 'executing';
  return 'queue';
}

/** 執行軌跡事件：準備＝隊列，調用＝執行中，結果＝已完成 */
export const TRACE_EVENT_COLUMNS: Record<WorkItemColumnKey, readonly string[]> = {
  queue: ['context_injection', 'phase_change', 'state_snapshot', 'memory_operation'],
  executing: ['llm_call', 'tool_call'],
  done: ['evaluation', 'reflection', 'improvement', 'error'],
};

export function traceEventColumn(event: string): WorkItemColumnKey {
  for (const col of WORK_ITEM_COLUMNS) {
    if (TRACE_EVENT_COLUMNS[col.key].includes(event)) return col.key;
  }
  return 'queue';
}

export function isLiveAgent(agent: Pick<RoleAgent, 'status'>): boolean {
  return agent.status === 'busy' || agent.status === 'waiting';
}

export function isAlertAgent(
  agent: Pick<RoleAgent, 'status' | 'alerts' | 'budget_over' | 'ai_budget_over' | 'cloud_budget_over'>,
): boolean {
  return (
    (agent.alerts?.length ?? 0) > 0 ||
    agent.status === 'error' ||
    !!agent.budget_over ||
    !!agent.ai_budget_over ||
    !!agent.cloud_budget_over
  );
}

export function fmtUsd(n: number): string {
  if (!n) return '$0';
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(3)}`;
}

export function lookupRateCard(
  modelId: string | undefined,
  catalog?: ModelRateCatalog | null,
): ModelRateCard | undefined {
  if (!modelId || !catalog?.by_id) return undefined;
  const bare = modelId.split('/').pop() || modelId;
  return catalog.by_id[modelId] || catalog.by_id[bare];
}

export function fmtPerMillion(n: number | undefined | null): string {
  if (n == null || Number.isNaN(Number(n))) return '—';
  const v = Number(n);
  if (v === 0) return '$0';
  if (Math.abs(v) < 0.01) return `$${v.toFixed(4)}`;
  if (Math.abs(v) < 1) return `$${v.toFixed(3)}`;
  return `$${v.toFixed(2)}`;
}

export function extraRateItems(card?: ModelRateCard | null): Array<{ id: string; label: string; usd_per_1m: number }> {
  return (card?.items ?? []).filter((item) => item.id !== 'input' && item.id !== 'output' && item.usd_per_1m);
}

export function rateOptionLabel(modelId: string, catalog?: ModelRateCatalog | null): string {
  const card = lookupRateCard(modelId, catalog);
  if (!card) return modelId;
  const extra = extraRateItems(card);
  const bits = [`${fmtPerMillion(card.input)} / ${fmtPerMillion(card.output)}`];
  if (extra.length) bits.push(`+${extra.length} 項`);
  return `${modelId} · ${bits.join(' · ')}`;
}

export function fmtWhen(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(11, 19) || iso;
  return d.toLocaleString('zh-TW', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export const JUMP_AGENT_EVENT = 'evoloop:jump-agent';
export const EDIT_API_ROUTE_EVENT = 'linkin:edit-api-route';
export const NEW_API_ROUTE_EVENT = 'linkin:new-api-route';
export const API_ROUTES_CHANGED_EVENT = 'linkin:api-routes-changed';

export const QUANT_DESK_ROLE_IDS = new Set([
  'finance_lead',
  'quant_analyst',
  'risk_analyst',
  'market_data_eng',
  'portfolio_mgr',
  'sentiment_analyst',
]);

export function isQuantDeskRole(id: string | null | undefined): boolean {
  return Boolean(id && QUANT_DESK_ROLE_IDS.has(id));
}

export type AgentDeskTab = 'tasks' | 'monitor' | 'settings' | 'quant' | 'grill' | 'overview' | 'org';
export type JumpAgentDetail = { id?: string; level?: number; rahoLayer?: number; deskTab?: AgentDeskTab };

/** 控制台跨頁：角色面板尚未掛載時先記下要開的工作台分頁。 */
let pendingDeskTab: AgentDeskTab | null = null;

export function setPendingDeskTab(tab: AgentDeskTab | null) {
  pendingDeskTab = tab;
}

export function requestRoleSettingsDesk(agentId?: string) {
  pendingDeskTab = 'settings';
  dispatchJumpAgent({ id: agentId, deskTab: 'settings' });
}

export function requestRoleGrillDesk(agentId?: string) {
  pendingDeskTab = 'grill';
  dispatchJumpAgent({ id: agentId, deskTab: 'grill' });
}

export function consumePendingDeskTab(): AgentDeskTab | null {
  const next = pendingDeskTab;
  pendingDeskTab = null;
  return next;
}

export function dispatchJumpAgent(detail: JumpAgentDetail) {
  window.dispatchEvent(new CustomEvent<JumpAgentDetail>(JUMP_AGENT_EVENT, { detail }));
}

export function dispatchEditApiRoute(routeId: string) {
  window.dispatchEvent(new CustomEvent<string>(EDIT_API_ROUTE_EVENT, { detail: routeId }));
}

export function dispatchNewApiRoute() {
  window.dispatchEvent(new Event(NEW_API_ROUTE_EVENT));
}

export function dispatchApiRoutesChanged() {
  window.dispatchEvent(new Event(API_ROUTES_CHANGED_EVENT));
}

export function isLinkinStudioAgent(agent: Pick<RoleAgent, 'id' | 'tags'> | string | null | undefined): boolean {
  if (!agent) return false;
  if (typeof agent === 'string') return agent.startsWith('custom_linkin_');
  const tags = agent.tags ?? [];
  return agent.id.startsWith('custom_linkin_') || tags.includes('linkin');
}

export type AgentDeskScope = 'console' | 'linkin';

export function filterAgentsByDesk(agents: RoleAgent[], desk: AgentDeskScope): RoleAgent[] {
  return agents.filter((agent) => (desk === 'linkin' ? isLinkinStudioAgent(agent) : !isLinkinStudioAgent(agent)));
}

export function pickDefaultAgentId(agents: RoleAgent[], preferred?: string | null): string {
  if (preferred === 'environment_kernel' || preferred === 'l0_kernel') {
    return '';
  }
  if (preferred === 'atomic_executor' || preferred === 'l2_executor') {
    const l2 = agents.find((a) => a.raho_layer === 2 || a.id === 'atomic_executor');
    if (l2) return l2.id;
  }
  if (preferred && agents.some((a) => a.id === preferred)) return preferred;
  const byLayer = preferred ? agents.find((a) => a.raho_layer === Number(preferred)) : undefined;
  if (byLayer) return byLayer.id;
  const busy = agents.find((a) => a.status === 'busy') ?? agents.find((a) => a.status === 'waiting' || a.status === 'error');
  if (busy) return busy.id;
  return agents.find((a) => a.id === 'manager')?.id ?? agents[0]?.id ?? '';
}

export function cleanRouteLabel(value: string): string {
  return value
    .replace(/[（(]單一廠商[)）]/g, '')
    .replace(/[（(]單一供應商[)）]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export function routeDisplayName(route?: { name?: string; provider_label?: string; provider?: string } | null): string {
  if (!route) return '';
  const name = cleanRouteLabel(route.name || '');
  const provider = cleanRouteLabel(route.provider_label || route.provider || '');
  if (name && provider && name !== provider) {
    if (name.includes(provider) || provider.includes(name)) {
      return name.length >= provider.length ? name : provider;
    }
    return `${name} · ${provider}`;
  }
  return name || provider;
}
