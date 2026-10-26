/**
 * 角色執行樹：把 fetchAgentMonitor 的 RoleAgent 收成可展開節點。
 * 狀態鍵對齊樹狀視圖（running / waiting / failed / idle / disabled），
 * 中文標籤沿用 AGENT_STATUS_META；queued / done / stopped 只在後端已有對應狀態時出現。
 * 階層只用名冊既有的 reporting_to／direct_reports，不另拉 RAHO 質詢鏈。
 */
import { AGENT_STATUS_META } from './agentUi';
import type { AgentCompanyTask, AgentWorkItem, RoleAgent } from '../types';

export type AgentTreeStatus =
  | 'running'
  | 'waiting'
  | 'failed'
  | 'idle'
  | 'disabled'
  | 'queued'
  | 'done'
  | 'stopped';

export interface AgentTreeNode {
  id: string;
  kind: 'role' | 'work';
  roleId: string;
  label: string;
  hint: string;
  status: AgentTreeStatus;
  statusLabel: string;
  sourceStatus: string;
  level: number;
  executing: number;
  queue: number;
  blocked: number;
  children: AgentTreeNode[];
}

export interface AgentTreeSummary {
  roles: number;
  running: number;
  waiting: number;
  failed: number;
  idle: number;
  disabled: number;
  work: number;
}

export type AgentTreeFocus = 'all' | 'live';

const ROLE_STATUS_TO_TREE: Record<string, AgentTreeStatus> = {
  busy: 'running',
  waiting: 'waiting',
  error: 'failed',
  idle: 'idle',
  disabled: 'disabled',
};

/** 後端工作項／公司任務已出現的狀態。未知值不對應到 queued／done／stopped。 */
const WORK_STATUS_TO_TREE: Record<string, AgentTreeStatus> = {
  planning: 'queued',
  ready: 'queued',
  pending: 'queued',
  executing: 'running',
  running: 'running',
  busy: 'running',
  in_review: 'waiting',
  rework: 'waiting',
  waiting: 'waiting',
  blocked: 'failed',
  error: 'failed',
  failed: 'failed',
  done: 'done',
  completed: 'done',
  cancelled: 'stopped',
  interrupted: 'stopped',
  idle: 'idle',
  disabled: 'disabled',
};

const TREE_LABEL: Record<AgentTreeStatus, string> = {
  running: AGENT_STATUS_META.busy.label,
  waiting: AGENT_STATUS_META.waiting.label,
  failed: AGENT_STATUS_META.error.label,
  idle: AGENT_STATUS_META.idle.label,
  disabled: AGENT_STATUS_META.disabled.label,
  queued: '排隊',
  done: '已完成',
  stopped: '已停止',
};

const ACTIVE_WORK: ReadonlySet<AgentTreeStatus> = new Set(['queued', 'running', 'waiting', 'failed']);

const LIVE_ROLE: ReadonlySet<AgentTreeStatus> = new Set(['running', 'waiting', 'failed']);

const KIND_LABEL: Record<string, string> = {
  assigned: '指派',
  execute: '執行',
  review: '審查',
  coordinate: '協調',
  synthesize: '整合',
  rework: '重修',
  decompose: '拆解',
  final_review: '終審',
  inspect: '驗收',
};

function compareText(a: string, b: string): number {
  return a.localeCompare(b, 'zh-Hant') || a.localeCompare(b);
}

function compareRoles(a: Pick<RoleAgent, 'level' | 'name' | 'id'>, b: Pick<RoleAgent, 'level' | 'name' | 'id'>): number {
  if (a.level !== b.level) return a.level - b.level;
  return compareText(a.name, b.name) || a.id.localeCompare(b.id);
}

export function mapRoleStatus(agent: Pick<RoleAgent, 'status' | 'enabled'>): { status: AgentTreeStatus; label: string } {
  if (agent.enabled === false || agent.status === 'disabled') {
    return { status: 'disabled', label: AGENT_STATUS_META.disabled.label };
  }
  const status = ROLE_STATUS_TO_TREE[agent.status];
  if (!status) return { status: 'idle', label: AGENT_STATUS_META.idle.label };
  return { status, label: AGENT_STATUS_META[agent.status]?.label ?? TREE_LABEL[status] };
}

export function mapWorkStatus(source: string): { status: AgentTreeStatus; label: string } | null {
  const status = WORK_STATUS_TO_TREE[source];
  if (!status) return null;
  if (source === 'failed') return { status, label: '失敗' };
  if (source === 'blocked' || source === 'error') return { status: 'failed', label: AGENT_STATUS_META.error.label };
  return { status, label: TREE_LABEL[status] };
}

function workHint(item: Pick<AgentWorkItem, 'kind' | 'phase'>): string {
  const kind = KIND_LABEL[item.kind] ?? '';
  const phase = (item.phase || '').trim();
  return [kind, phase].filter(Boolean).join(' · ');
}

function workNode(roleId: string, id: string, label: string, hint: string, source: string, level = 99): AgentTreeNode | null {
  const mapped = mapWorkStatus(source);
  if (!mapped || !ACTIVE_WORK.has(mapped.status)) return null;
  return {
    id,
    kind: 'work',
    roleId,
    label: label.trim() || id,
    hint,
    status: mapped.status,
    statusLabel: mapped.label,
    sourceStatus: source,
    level,
    executing: 0,
    queue: 0,
    blocked: 0,
    children: [],
  };
}

const WORK_RANK: Record<AgentTreeStatus, number> = {
  failed: 0,
  running: 1,
  waiting: 2,
  queued: 3,
  stopped: 4,
  done: 5,
  idle: 6,
  disabled: 7,
};

function activeWorkNodes(agent: RoleAgent): AgentTreeNode[] {
  const items = agent.work_items ?? [];
  const nodes: AgentTreeNode[] = [];
  const covered = new Set<string>();
  for (const item of items) {
    if (item.task_id) covered.add(item.task_id);
    const node = workNode(
      agent.id,
      `work:${agent.id}:${item.task_id}:${item.id}:${item.kind}`,
      item.title || item.task_query || item.id,
      workHint(item),
      item.status,
    );
    if (node) nodes.push(node);
  }
  nodes.sort((a, b) => WORK_RANK[a.status] - WORK_RANK[b.status] || compareText(a.label, b.label));

  const extras: AgentTreeNode[] = [];
  for (const task of agent.company_tasks ?? []) {
    if (!task.task_id || covered.has(task.task_id)) continue;
    const node = companyTaskNode(agent.id, task);
    if (node) extras.push(node);
  }
  extras.sort((a, b) => WORK_RANK[a.status] - WORK_RANK[b.status] || compareText(a.label, b.label));
  return [...nodes, ...extras];
}

function companyTaskNode(roleId: string, task: AgentCompanyTask): AgentTreeNode | null {
  return workNode(
    roleId,
    `task:${roleId}:${task.task_id}`,
    task.query || task.task_id,
    task.phase || '公司任務',
    task.status,
  );
}

function resolveParents(agents: RoleAgent[]): Map<string, string | null> {
  const byId = new Map(agents.map((agent) => [agent.id, agent]));
  const viaDirect = new Map<string, string>();
  const ordered = [...agents].sort(compareRoles);
  for (const agent of ordered) {
    for (const childId of agent.direct_reports ?? []) {
      if (!childId || childId === agent.id || !byId.has(childId) || viaDirect.has(childId)) continue;
      viaDirect.set(childId, agent.id);
    }
  }

  const parentOf = new Map<string, string | null>();
  for (const agent of agents) {
    const reported = agent.reporting_to;
    if (reported && reported !== agent.id && byId.has(reported)) {
      parentOf.set(agent.id, reported);
      continue;
    }
    parentOf.set(agent.id, viaDirect.get(agent.id) ?? null);
  }

  for (const start of parentOf.keys()) {
    const seen = new Set<string>();
    let cursor: string | null = start;
    while (cursor) {
      if (seen.has(cursor)) {
        parentOf.set(cursor, null);
        break;
      }
      seen.add(cursor);
      cursor = parentOf.get(cursor) ?? null;
    }
  }
  return parentOf;
}

function roleNode(agent: RoleAgent, children: AgentTreeNode[]): AgentTreeNode {
  const mapped = mapRoleStatus(agent);
  const work = activeWorkNodes(agent);
  return {
    id: `role:${agent.id}`,
    kind: 'role',
    roleId: agent.id,
    label: agent.name,
    hint: agent.raho_short || agent.level_label || '',
    status: mapped.status,
    statusLabel: mapped.label,
    sourceStatus: agent.status,
    level: agent.level,
    executing: agent.executing ?? 0,
    queue: agent.queue ?? 0,
    blocked: agent.blocked ?? 0,
    children: [...children, ...work],
  };
}

export function buildAgentExecutionTree(agents: RoleAgent[]): AgentTreeNode[] {
  if (!agents.length) return [];
  const byId = new Map(agents.map((agent) => [agent.id, agent]));
  const parentOf = resolveParents(agents);
  const childIds = new Map<string, string[]>();
  const roots: string[] = [];
  for (const agent of agents) {
    const parent = parentOf.get(agent.id);
    if (!parent || parent === agent.id || !byId.has(parent)) {
      roots.push(agent.id);
      continue;
    }
    const list = childIds.get(parent) ?? [];
    list.push(agent.id);
    childIds.set(parent, list);
  }

  const build = (id: string, stack: Set<string>): AgentTreeNode | null => {
    if (stack.has(id)) return null;
    const agent = byId.get(id);
    if (!agent) return null;
    const next = new Set(stack);
    next.add(id);
    const roles = (childIds.get(id) ?? [])
      .map((childId) => build(childId, next))
      .filter((node): node is AgentTreeNode => node != null)
      .sort((a, b) => a.level - b.level || compareText(a.label, b.label));
    return roleNode(agent, roles);
  };

  return roots
    .map((id) => build(id, new Set()))
    .filter((node): node is AgentTreeNode => node != null)
    .sort((a, b) => a.level - b.level || compareText(a.label, b.label));
}

export function summarizeAgentTree(nodes: AgentTreeNode[]): AgentTreeSummary {
  const summary: AgentTreeSummary = {
    roles: 0,
    running: 0,
    waiting: 0,
    failed: 0,
    idle: 0,
    disabled: 0,
    work: 0,
  };
  const walk = (node: AgentTreeNode) => {
    if (node.kind === 'role') {
      summary.roles += 1;
      if (node.status === 'running') summary.running += 1;
      else if (node.status === 'waiting') summary.waiting += 1;
      else if (node.status === 'failed') summary.failed += 1;
      else if (node.status === 'disabled') summary.disabled += 1;
      else summary.idle += 1;
    } else {
      summary.work += 1;
    }
    node.children.forEach(walk);
  };
  nodes.forEach(walk);
  return summary;
}

export function filterAgentTree(nodes: AgentTreeNode[], query: string): AgentTreeNode[] {
  const q = query.trim().toLowerCase();
  if (!q) return nodes;
  const visit = (node: AgentTreeNode): AgentTreeNode | null => {
    const hay = `${node.label} ${node.hint} ${node.roleId} ${node.statusLabel} ${node.sourceStatus}`.toLowerCase();
    if (hay.includes(q)) return node;
    const children = node.children.map(visit).filter((child): child is AgentTreeNode => child != null);
    if (!children.length) return null;
    return { ...node, children };
  };
  return nodes.map(visit).filter((node): node is AgentTreeNode => node != null);
}

export function focusAgentTree(nodes: AgentTreeNode[], focus: AgentTreeFocus): AgentTreeNode[] {
  if (focus !== 'live') return nodes;
  const visit = (node: AgentTreeNode): AgentTreeNode | null => {
    const children = node.children.map(visit).filter((child): child is AgentTreeNode => child != null);
    if (node.kind === 'work') {
      return ACTIVE_WORK.has(node.status) ? { ...node, children } : null;
    }
    if (LIVE_ROLE.has(node.status) || children.length) return { ...node, children };
    return null;
  };
  return nodes.map(visit).filter((node): node is AgentTreeNode => node != null);
}

/** 預設展開：根節點的下一層，以及執行中／等待／阻塞的席位。 */
export function defaultOpenIds(nodes: AgentTreeNode[]): string[] {
  const ids: string[] = [];
  const walk = (node: AgentTreeNode, depth: number) => {
    if (node.kind !== 'role' || node.children.length === 0) return;
    const hasRoleChild = node.children.some((child) => child.kind === 'role');
    if ((depth === 0 && hasRoleChild) || LIVE_ROLE.has(node.status)) ids.push(node.id);
    for (const child of node.children) {
      if (child.kind === 'role') walk(child, depth + 1);
    }
  };
  nodes.forEach((node) => walk(node, 0));
  return ids;
}

export function branchIds(nodes: AgentTreeNode[]): string[] {
  const ids: string[] = [];
  const walk = (node: AgentTreeNode) => {
    if (node.kind === 'role' && node.children.length) ids.push(node.id);
    node.children.forEach(walk);
  };
  nodes.forEach(walk);
  return ids;
}

/** 選中席位時展開其祖先；席位本身有子節點也展開。 */
export function ancestorOpenIds(nodes: AgentTreeNode[], roleId: string): string[] {
  const ids: string[] = [];
  const walk = (node: AgentTreeNode, ancestors: string[]): boolean => {
    if (node.kind === 'role' && node.roleId === roleId) {
      ids.push(...ancestors);
      if (node.children.length) ids.push(node.id);
      return true;
    }
    for (const child of node.children) {
      if (child.kind !== 'role') continue;
      if (walk(child, [...ancestors, node.id])) return true;
    }
    return false;
  };
  for (const node of nodes) {
    if (walk(node, [])) break;
  }
  return ids;
}
