/**
 * RAHO 層級／角色統一顯示（與 backend/company/raho/protocol.py 對齊）。
 * 三條線：指揮鏈 L5→L4→L3→L2、獨立審查 L1、環境核心 L0。
 * 質詢樹、角色名冊、工作台必須走這份資料，禁止各面板自寫 L0–L5 名稱。
 */
import type { GrillTree, GrillTreeNode, RahoDirectoryEntry, RahoGrillEdge, RoleAgent } from '../types';
import { requestRoleGrillDesk } from './agentUi';

export const RAHO_CHAIN = [5, 4, 3, 2, 1, 0] as const;
export const COMMAND_CHAIN = [5, 4, 3, 2] as const;
export const INSPECT_CHAIN = [1] as const;
export const KERNEL_CHAIN = [0] as const;

export const LANE_LABELS: Record<string, string> = {
  kernel: '環境核心',
  command: '指揮鏈',
  inspect: '獨立審查',
};

export const DIRECTION_LABELS: Record<string, string> = {
  up: '質詢上拋',
  down: '任務下達',
  inspect: '獨立審查',
  inject: '環境注入',
};

export const DIRECTION_GLYPH: Record<string, string> = {
  up: '↑',
  down: '↓',
  inspect: '⇄',
  inject: '⇢',
};

export const RAHO_LAYERS: Record<number, RahoDirectoryEntry> = {
  0: {
    layer: 0,
    id: 'l0_kernel',
    role_id: 'environment_kernel',
    title: '環境與記憶核心',
    short: 'L0 核心',
    full: 'L0 環境與記憶核心',
    lane: 'kernel',
    lane_label: '環境核心',
    grill_targets: [],
    escalate_targets: [],
    submit_targets: [],
    reports_to: null,
    independent: true,
  },
  1: {
    layer: 1,
    id: 'l1_inspector',
    role_id: 'constitutional_inspector',
    title: '憲兵審查官',
    short: 'L1 憲兵',
    full: 'L1 憲兵審查官',
    lane: 'inspect',
    lane_label: '獨立審查',
    grill_targets: ['atomic_executor', 'tactical_commander'],
    grill_target_labels: ['L2 原子執行者', 'L3 戰術指揮官'],
    escalate_targets: ['requirement_auditor', 'user'],
    submit_targets: [],
    reports_to: null,
    independent: true,
  },
  2: {
    layer: 2,
    id: 'l2_executor',
    role_id: 'atomic_executor',
    title: '原子執行者',
    short: 'L2 執行',
    full: 'L2 原子執行者',
    lane: 'command',
    lane_label: '指揮鏈',
    grill_targets: ['tactical_commander'],
    grill_target_labels: ['L3 戰術指揮官'],
    escalate_targets: ['tactical_commander', 'requirement_auditor', 'user'],
    submit_targets: ['constitutional_inspector'],
    submit_target_labels: ['L1 憲兵審查官'],
    reports_to: 'tactical_commander',
    independent: false,
  },
  3: {
    layer: 3,
    id: 'l3_commander',
    role_id: 'tactical_commander',
    title: '戰術指揮官',
    short: 'L3 指揮',
    full: 'L3 戰術指揮官',
    lane: 'command',
    lane_label: '指揮鏈',
    grill_targets: ['requirement_auditor'],
    grill_target_labels: ['L4 需求審計官'],
    escalate_targets: ['requirement_auditor', 'user'],
    submit_targets: ['atomic_executor'],
    submit_target_labels: ['L2 原子執行者'],
    reports_to: 'requirement_auditor',
    independent: false,
  },
  4: {
    layer: 4,
    id: 'l4_auditor',
    role_id: 'requirement_auditor',
    title: '需求審計官',
    short: 'L4 審計',
    full: 'L4 需求審計官',
    lane: 'command',
    lane_label: '指揮鏈',
    grill_targets: ['user'],
    grill_target_labels: ['L5 用戶'],
    escalate_targets: ['user'],
    submit_targets: ['tactical_commander'],
    submit_target_labels: ['L3 戰術指揮官'],
    reports_to: 'user',
    independent: false,
  },
  5: {
    layer: 5,
    id: 'l5_user',
    role_id: 'user',
    title: '用戶',
    short: 'L5 用戶',
    full: 'L5 用戶',
    lane: 'command',
    lane_label: '指揮鏈',
    grill_targets: [],
    escalate_targets: [],
    submit_targets: ['requirement_auditor'],
    submit_target_labels: ['L4 需求審計官'],
    reports_to: null,
    independent: true,
  },
};

function edge(
  fromLayer: number,
  toLayer: number,
  kind: string,
  label: string,
  direction: RahoGrillEdge['direction'],
): RahoGrillEdge {
  const src = RAHO_LAYERS[fromLayer];
  const dst = RAHO_LAYERS[toLayer];
  return {
    from_layer: fromLayer,
    to_layer: toLayer,
    from_role: src.role_id,
    to_role: dst.role_id,
    from_label: src.full,
    to_label: dst.full,
    kind,
    label,
    direction,
    lane: direction === 'inject' ? 'kernel' : direction === 'inspect' ? 'inspect' : 'command',
  };
}

export const GRILL_EDGES: RahoGrillEdge[] = [
  edge(5, 4, 'mandate', '提交需求', 'down'),
  edge(4, 3, 'campaign', '戰術指令下達', 'down'),
  edge(3, 2, 'campaign', '孵化原子任務', 'down'),
  edge(2, 1, 'submit', '提交產出驗收', 'inspect'),
  edge(4, 5, 'user_grill', '需求審計', 'up'),
  edge(3, 4, 'escalate', '戰略不可行', 'up'),
  edge(3, 5, 'escalate', '基礎設施缺失', 'up'),
  edge(2, 3, 'mgp', '戰前質詢', 'up'),
  edge(2, 4, 'escalate', '戰前逾時跳級', 'up'),
  edge(1, 2, 'rework', '退回重做', 'inspect'),
  edge(1, 3, 'inspect', '質疑規劃', 'inspect'),
  edge(1, 4, 'escalate', '標準爭議', 'up'),
  edge(1, 5, 'escalate', '最終裁定', 'up'),
  edge(0, 4, 'l0', '滲透決策層', 'inject'),
  edge(0, 3, 'l0', '滲透規劃層', 'inject'),
  edge(0, 2, 'l0', '滲透執行層', 'inject'),
  edge(0, 1, 'l0', '滲透審查層', 'inject'),
];

export const RAHO_SPINE_ROLE_IDS = [
  'environment_kernel',
  'requirement_auditor',
  'tactical_commander',
  'atomic_executor',
  'constitutional_inspector',
  'user',
] as const;

export const RAHO_KIND_LABELS: Record<string, string> = {
  mandate: '需求下達',
  user_grill: '用戶審計',
  mgp: '戰前質詢',
  escalate: '向上呈報',
  resolve: '解除阻塞',
  timeout: '決策逾時',
  user_decide: '用戶裁決',
  inspect: '憲兵審查',
  submit: '提交驗收',
  campaign: '戰役下達',
  rework: '退回重做',
  l0: '環境注入',
  memory: '記憶回放',
  knowledge: '知識引用',
};

export const RAHO_STATUS_LABELS: Record<string, string> = {
  open: '待回覆',
  blocked: '阻塞',
  resolved: '已解除',
  escalated: '已跳級',
  timeout: '逾時',
};

const ROLE_LAYER: Record<string, number> = {
  environment_kernel: 0,
  constitutional_inspector: 1,
  reviewer: 1,
  atomic_executor: 2,
  tactical_commander: 3,
  requirement_auditor: 4,
  manager: 4,
  user: 5,
};

export function rahoLayerOf(roleId?: string | null, fallback?: number | null): number {
  if (roleId && Object.prototype.hasOwnProperty.call(ROLE_LAYER, roleId)) {
    return ROLE_LAYER[roleId];
  }
  if (fallback != null && RAHO_LAYERS[fallback]) return fallback;
  if (roleId?.endsWith('_lead') || roleId === 'architect' || roleId === 'coordinator') return 3;
  return 2;
}

export function rahoMeta(layer?: number | null): RahoDirectoryEntry {
  return RAHO_LAYERS[layer ?? 2] ?? RAHO_LAYERS[2];
}

export function rahoLayerLabel(layer?: number | null, short = false): string {
  const meta = rahoMeta(layer);
  return short ? meta.short : meta.full;
}

export function rahoRoleLabel(roleId?: string | null, layer?: number | null): string {
  if (roleId === 'manager') return 'L4 專案經理';
  if (roleId === 'reviewer') return 'L1 審查者';
  const resolved = rahoLayerOf(roleId, layer);
  return rahoLayerLabel(resolved);
}

export function isRahoSpineRole(id?: string | null): boolean {
  return Boolean(id && (RAHO_SPINE_ROLE_IDS as readonly string[]).includes(id));
}

export function kindLabel(kind?: string | null, catalog?: Record<string, string>): string {
  const key = kind || '';
  return catalog?.[key] || RAHO_KIND_LABELS[key] || key || '質詢';
}

export function directionLabel(direction?: string | null): string {
  const key = direction || '';
  return DIRECTION_LABELS[key] || key || '質詢';
}

export function directionGlyph(direction?: string | null): string {
  const key = direction || '';
  return DIRECTION_GLYPH[key] || '→';
}

export function laneLabel(lane?: string | null): string {
  const key = lane || '';
  return LANE_LABELS[key] || key || '指揮鏈';
}

export function statusLabel(status?: string | null): string {
  const key = status || '';
  return RAHO_STATUS_LABELS[key] || key;
}

export function canonicalRoleId(layer?: number | null, roleId?: string | null): string {
  if (roleId && roleId !== 'user') {
    if (roleId === 'l2_executor') return 'atomic_executor';
    if (roleId === 'l0_kernel') return 'environment_kernel';
    return roleId;
  }
  return rahoMeta(layer).role_id;
}

export function isCanonicalLayerRole(roleId?: string | null): boolean {
  if (!roleId) return false;
  return Object.values(RAHO_LAYERS).some((meta) => meta.role_id === roleId);
}

export function nodeRoleId(node: GrillTreeNode, side: 'from' | 'to'): string {
  const id = side === 'from' ? node.from_role : node.to_role;
  const layer = side === 'from' ? node.from_layer : node.to_layer;
  return canonicalRoleId(layer, id);
}

export function nodeRoleLabel(node: GrillTreeNode, side: 'from' | 'to'): string {
  const explicit = side === 'from' ? node.from_label : node.to_label;
  if (explicit) return explicit;
  const layer = side === 'from' ? node.from_layer : node.to_layer;
  const role = side === 'from' ? node.from_role : node.to_role;
  return rahoRoleLabel(role, layer);
}

export function agentRahoLabel(
  agent: Pick<RoleAgent, 'id' | 'name' | 'raho_label' | 'raho_layer' | 'raho_spine'>,
): string {
  if (agent.raho_label) return agent.raho_label;
  if (isRahoSpineRole(agent.id) || agent.raho_spine) return rahoRoleLabel(agent.id, agent.raho_layer);
  const layer = rahoLayerOf(agent.id, agent.raho_layer);
  return agent.name ? `L${layer} ${agent.name}` : rahoLayerLabel(layer);
}

export function grillTargetLabel(roleId?: string | null): string {
  if (!roleId) return '';
  const layer = ROLE_LAYER[roleId];
  if (layer != null) return RAHO_LAYERS[layer]?.full || roleId;
  return rahoRoleLabel(roleId);
}

export function orgLevelCaption(
  agent: Pick<RoleAgent, 'level' | 'level_label' | 'raho_spine' | 'raho_independent' | 'raho_lane' | 'raho_lane_label' | 'reporting_to'>,
): string {
  if (agent.raho_spine) {
    const lane = agent.raho_lane_label || laneLabel(agent.raho_lane);
    if (agent.raho_independent || !agent.reporting_to) return `${lane} · 獨立`;
    return `${lane} · 上報 ${grillTargetLabel(agent.reporting_to)}`;
  }
  return `組織 · ${agent.level_label || `職級 ${agent.level}`}`;
}

export function edgesForRole(roleId: string, edges?: RahoGrillEdge[] | null): RahoGrillEdge[] {
  const list = edges && edges.length ? edges : GRILL_EDGES;
  return list.filter((edge) => edge.from_role === roleId || edge.to_role === roleId);
}

export function nodesForRole(trees: GrillTree[], roleId: string): GrillTreeNode[] {
  const layer = rahoLayerOf(roleId);
  const canonical = rahoMeta(layer).role_id;
  const matchLayer = Boolean(canonical && roleId === canonical);
  const out: GrillTreeNode[] = [];
  const seen = new Set<string>();
  for (const tree of trees) {
    for (const node of tree.nodes ?? []) {
      const hit =
        nodeRoleId(node, 'from') === roleId ||
        nodeRoleId(node, 'to') === roleId ||
        (matchLayer && (node.from_layer === layer || node.to_layer === layer));
      if (!hit || seen.has(node.node_id)) continue;
      seen.add(node.node_id);
      out.push(node);
    }
  }
  return out.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
}

export function openCountForRole(trees: GrillTree[], roleId: string): number {
  return nodesForRole(trees, roleId).filter((n) => n.status === 'open' || n.status === 'blocked').length;
}

export function jumpToRoleDesk(roleId: string) {
  if (!roleId || roleId === 'user' || roleId === 'environment_kernel') {
    if (roleId === 'environment_kernel') jumpToL0Kernel();
    return;
  }
  window.location.hash = `#/monitor/agents/${encodeURIComponent(roleId)}`;
}

export function jumpToGrillTree(roleId?: string) {
  const target = roleId && roleId !== 'user' ? roleId : undefined;
  if (target === 'environment_kernel') {
    jumpToL0Kernel();
    return;
  }
  requestRoleGrillDesk(target);
  if (target) {
    window.location.hash = `#/monitor/agents/${encodeURIComponent(target)}`;
    return;
  }
  window.location.hash = '#/monitor/agents';
}

export function jumpToL0Kernel() {
  window.location.hash = '#/monitor/memory';
}

/** Context：優先開對話詳細區；僅在明確要控制台鏡像時走 hash。 */
export function jumpToContextMonitor(taskId?: string, opts?: { mirror?: boolean }) {
  if (opts?.mirror) {
    if (taskId) {
      window.location.hash = `#/monitor/context/${encodeURIComponent(taskId)}`;
      return;
    }
    window.location.hash = '#/monitor/context';
    return;
  }
  // 動態匯入避免與 contextUi 循環依賴
  void import('./contextUi').then(({ openChatContextDetail }) => {
    openChatContextDetail(taskId ?? null);
  });
}

/** 外部整合控制台（MemOS／OpenViking／WeKnora／Yao／Ouroboros／OpenPencil）。 */
export function jumpToIntegrations(name?: string) {
  if (name) {
    window.location.hash = `#/monitor/integrations/${encodeURIComponent(name)}`;
    return;
  }
  window.location.hash = '#/monitor/integrations';
}

export function jumpLayer(layer: number, roleId?: string) {
  const canonical = canonicalRoleId(layer, roleId);
  if (layer === 0 || canonical === 'environment_kernel') {
    jumpToL0Kernel();
    return;
  }
  if (layer === 5 || canonical === 'user') return;
  jumpToRoleDesk(canonical);
}

export function rahoTone(status: string): string {
  if (status === 'blocked' || status === 'open') return 'var(--apple-red)';
  if (status === 'timeout') return 'var(--apple-orange, #FF9F0A)';
  if (status === 'escalated') return '#BF5AF2';
  return 'var(--apple-green)';
}
