/**
 * 任務詳情整頁的型別收窄與安全取值。
 *
 * 專案的 `types.ts` 不由本頁維護，但後端 `GET /api/tasks/{id}` 實際回傳的
 * `plan`／`raho` 比宣告還多（campaign、battle_plan、commander），
 * `raho.blocked` 更混入了待決決策。所有超出宣告的欄位一律在此收窄，
 * 不修改 types.ts。
 */
import type {
  AuditorTicket,
  BattlePlan,
  CampaignMap,
  GrillTree,
  GrillTreeNode,
  KanbanItem,
  RahoSnapshot,
  TaskProgress,
} from '../../types';

/** `task.plan` 的實際後端载荷（types.ts 只宣告前三鍵）。 */
export interface PlanPayload {
  subtask_count?: number;
  strategy?: string;
  execution_plan?: unknown;
  campaign?: CampaignMap;
  battle_plan?: BattlePlan | null;
  commander?: Record<string, unknown> | null;
}

/** `task.raho` 的實際後端載荷。 */
export type RahoPayload = RahoSnapshot & {
  battle_plan?: BattlePlan | null;
  commander?: Record<string, unknown> | null;
};

/** `raho.blocked` 除質詢節點外也會混入待決決策（缺 node_id、帶 question）。 */
export type BlockedNode = GrillTreeNode & {
  decision_id?: string;
  question?: string;
  role_label?: string;
  layer?: number;
  item_id?: string;
};

/** 看板狀態字面值（對應 backend/company/state.py::WorkItemStatus）。 */
export const KANBAN_STATUS_ORDER = [
  'planning',
  'ready',
  'executing',
  'in_review',
  'rework',
  'done',
  'blocked',
] as const;

export function planOf(task: TaskProgress | null): PlanPayload | null {
  if (!task || !task.plan) return null;
  return task.plan as unknown as PlanPayload;
}

export function rahoOf(task: TaskProgress | null): RahoPayload | null {
  if (!task || !task.raho) return null;
  return task.raho as RahoPayload;
}

export function ticketOf(task: TaskProgress | null): AuditorTicket | null {
  return task?.options?.auditor_ticket ?? null;
}

/** 戰役地圖優先級：plan.campaign → raho.campaign → raho.tree.campaign。 */
export function campaignOf(task: TaskProgress | null): CampaignMap | null {
  const raho = rahoOf(task);
  const pick = (c: CampaignMap | null | undefined): CampaignMap | null =>
    c && (c.nodes?.length || c.goal || c.success_criteria?.length) ? c : null;
  return (
    pick(planOf(task)?.campaign) ??
    pick(raho?.campaign) ??
    pick(raho?.tree?.campaign) ??
    pick(raho?.trees?.find((t) => t.campaign?.nodes?.length)?.campaign) ??
    null
  );
}

export function battlePlanOf(task: TaskProgress | null): BattlePlan | null {
  return rahoOf(task)?.battle_plan ?? planOf(task)?.battle_plan ?? null;
}

export function commanderOf(task: TaskProgress | null): Record<string, unknown> | null {
  const raw = rahoOf(task)?.commander ?? planOf(task)?.commander;
  return asRecord(raw);
}

/** 本任務要呈現的質詢樹：tree 優先，其餘 trees 去重後併入。 */
export function treesOf(task: TaskProgress | null): GrillTree[] {
  const raho = rahoOf(task);
  const out: GrillTree[] = [];
  const seen = new Set<string>();
  const push = (tree: GrillTree | null | undefined) => {
    if (!tree) return;
    const key = tree.tree_id || tree.run_id || '';
    if (key && seen.has(key)) return;
    if (key) seen.add(key);
    out.push(tree);
  };
  push(raho?.tree);
  for (const t of raho?.trees ?? []) push(t);
  return out.filter((t) => (t.nodes?.length ?? 0) > 0 || t.goal || t.campaign?.nodes?.length);
}

export function allKanbanItems(task: TaskProgress | null): KanbanItem[] {
  const out: KanbanItem[] = [];
  for (const status of KANBAN_STATUS_ORDER) {
    for (const item of (task?.kanban?.[status] ?? []) as KanbanItem[]) {
      if (item) out.push(item);
    }
  }
  for (const [status, items] of Object.entries(task?.kanban ?? {})) {
    if ((KANBAN_STATUS_ORDER as readonly string[]).includes(status)) continue;
    for (const item of (items ?? []) as KanbanItem[]) if (item) out.push(item);
  }
  return out;
}

// ── 安全取值 ──

export function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function num(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

/** 任何值轉成可顯示字串（物件退回 JSON）。 */
export function textField(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value, null, 2) ?? '';
  } catch {
    return String(value);
  }
}

export function listOf(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(textField).map((s) => s.trim()).filter(Boolean);
  const single = textField(value).trim();
  return single ? [single] : [];
}

export function pct(value: unknown): number | null {
  const n = num(value);
  return n == null ? null : Math.max(0, Math.min(100, n));
}

export function pick(row: Record<string, unknown> | null | undefined, key: string): unknown {
  return row ? row[key] : undefined;
}

/** 從物件中挑掉已單獨呈現的鍵，剩下的一律給 JSON 兜底。 */
export function restKeys(
  row: Record<string, unknown> | null | undefined,
  used: string[],
): Record<string, unknown> {
  if (!row) return {};
  const skip = new Set(used);
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(row)) if (!skip.has(k)) out[k] = v;
  return out;
}

/** ISO 字串或 Unix 秒皆可；都失效時回 '—'。 */
export function timeText(value: unknown): string {
  if (value == null || value === '') return '—';
  const raw = typeof value === 'number' ? String(value) : String(value).trim();
  if (/^\d+(\.\d+)?$/.test(raw)) {
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0) return '—';
    const ms = n > 1e11 ? n : n * 1000;
    const d = new Date(ms);
    if (Number.isNaN(d.getTime())) return '—';
    return d.toLocaleString('zh-TW', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  }
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString('zh-TW', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}
