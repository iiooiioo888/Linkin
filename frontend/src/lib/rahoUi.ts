/**
 * RAHO 層級／角色統一顯示（與 backend/company/raho/protocol.py 對齊）。
 * 質詢樹、角色名冊、工作台必須走這份資料，禁止各面板自寫 L1–L5 名稱。
 */
import type { GrillTree, GrillTreeNode, RahoDirectoryEntry, RoleAgent } from '../types';

export const RAHO_LAYERS: Record<number, RahoDirectoryEntry> = {
  1: {
    layer: 1,
    id: 'l1_inspector',
    role_id: 'constitutional_inspector',
    title: '憲兵審查官',
    short: 'L1 憲兵',
    full: 'L1 憲兵審查官',
    grill_targets: ['L2 原子執行者', 'L3 戰術指揮官'],
  },
  2: {
    layer: 2,
    id: 'l2_executor',
    role_id: '',
    title: '原子執行者',
    short: 'L2 執行',
    full: 'L2 原子執行者',
    grill_targets: ['L3 戰術指揮官'],
  },
  3: {
    layer: 3,
    id: 'l3_commander',
    role_id: 'tactical_commander',
    title: '戰術指揮官',
    short: 'L3 指揮',
    full: 'L3 戰術指揮官',
    grill_targets: ['L4 需求審計官', 'L5 用戶'],
  },
  4: {
    layer: 4,
    id: 'l4_auditor',
    role_id: 'requirement_auditor',
    title: '需求審計官',
    short: 'L4 審計',
    full: 'L4 需求審計官',
    grill_targets: ['L5 用戶'],
  },
  5: {
    layer: 5,
    id: 'l5_user',
    role_id: 'user',
    title: '用戶',
    short: 'L5 用戶',
    full: 'L5 用戶',
    grill_targets: [],
  },
};

export const RAHO_SPINE_ROLE_IDS = [
  'requirement_auditor',
  'tactical_commander',
  'constitutional_inspector',
] as const;

export const RAHO_KIND_LABELS: Record<string, string> = {
  user_grill: '用戶審計',
  mgp: '戰前質詢',
  escalate: '向上呈報',
  resolve: '解除阻塞',
  timeout: '決策逾時',
  user_decide: '用戶裁決',
  inspect: '憲兵審查',
  campaign: '戰役下達',
  rework: '退回重做',
};

export const RAHO_STATUS_LABELS: Record<string, string> = {
  open: '待回覆',
  blocked: '阻塞',
  resolved: '已解除',
  escalated: '已跳級',
  timeout: '逾時',
};

const ROLE_LAYER: Record<string, number> = {
  constitutional_inspector: 1,
  reviewer: 1,
  tactical_commander: 3,
  requirement_auditor: 4,
  manager: 4,
  user: 5,
};

export function rahoLayerOf(roleId?: string | null, fallback?: number | null): number {
  if (roleId && ROLE_LAYER[roleId]) return ROLE_LAYER[roleId];
  if (fallback && RAHO_LAYERS[fallback]) return fallback;
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

export function statusLabel(status?: string | null): string {
  const key = status || '';
  return RAHO_STATUS_LABELS[key] || key;
}

export function nodeRoleId(node: GrillTreeNode, side: 'from' | 'to'): string {
  const id = side === 'from' ? node.from_role : node.to_role;
  if (id && id !== 'user') return id;
  const layer = side === 'from' ? node.from_layer : node.to_layer;
  return rahoMeta(layer).role_id;
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

export function orgLevelCaption(agent: Pick<RoleAgent, 'level' | 'level_label'>): string {
  return `組織 · ${agent.level_label || `職級 ${agent.level}`}`;
}

export function nodesForRole(trees: GrillTree[], roleId: string): GrillTreeNode[] {
  const out: GrillTreeNode[] = [];
  for (const tree of trees) {
    for (const node of tree.nodes ?? []) {
      if (nodeRoleId(node, 'from') === roleId || nodeRoleId(node, 'to') === roleId) {
        out.push(node);
      }
    }
  }
  return out.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
}

export function openCountForRole(trees: GrillTree[], roleId: string): number {
  return nodesForRole(trees, roleId).filter((n) => n.status === 'open' || n.status === 'blocked').length;
}

export function jumpToRoleDesk(roleId: string) {
  if (!roleId || roleId === 'user') return;
  window.location.hash = `#/monitor/agents/${encodeURIComponent(roleId)}`;
}

export function jumpToGrillTree() {
  window.location.hash = '#/monitor/grill';
}

export function rahoTone(status: string): string {
  if (status === 'blocked' || status === 'open') return 'var(--apple-red)';
  if (status === 'timeout') return 'var(--apple-orange, #FF9F0A)';
  if (status === 'escalated') return '#BF5AF2';
  return 'var(--apple-green)';
}
