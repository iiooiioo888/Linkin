/**
 * 看板欄位、節點轉換與角色頭像／標籤 helpers。
 */
import type { KanbanItem, TaskProgress } from '../../types';

export const WS_KANBAN_COLUMNS = [
  { key: 'queue', label: '隊列', statuses: ['planning', 'ready', 'blocked', 'cancelled'] },
  { key: 'executing', label: '執行中', statuses: ['executing', 'rework'] },
  { key: 'review', label: '審查中', statuses: ['in_review', 'done'] },
] as const;

export type WsColumnKey = (typeof WS_KANBAN_COLUMNS)[number]['key'];

export interface WsNode {
  item: KanbanItem;
  status: string;
  column: WsColumnKey;
  tags: string[];
  progress: number;
  action: string;
}

const AVATAR_COLORS = ['#c9a961', '#7a92b8', '#6fa87f', '#82828c', '#9184b5', '#7aa8b8'];

const STATUS_PROGRESS: Record<string, number> = {
  planning: 0,
  ready: 8,
  blocked: 12,
  executing: 55,
  rework: 40,
  in_review: 100,
  done: 100,
};

export function wsColumnKey(status: string): WsColumnKey {
  for (const col of WS_KANBAN_COLUMNS) {
    if ((col.statuses as readonly string[]).includes(status)) return col.key;
  }
  return 'queue';
}

export function flattenWsNodes(task: TaskProgress | null | undefined): WsNode[] {
  if (!task?.kanban) return [];
  const rows: WsNode[] = [];
  for (const [status, items] of Object.entries(task.kanban)) {
    for (const item of items) {
      rows.push({
        item,
        status,
        column: wsColumnKey(status),
        tags: wsNodeTags(item, status),
        progress: wsNodeProgress(item, status),
        action: String(item.current_action || '').trim(),
      });
    }
  }
  return rows;
}

export function nodeCode(id: string): string {
  const raw = String(id || '').trim();
  if (!raw) return 'NODE';
  if (/^n(ode)?[-_]?\w+/i.test(raw)) return raw.replace(/^node[-_]?/i, 'NODE-').toUpperCase();
  return `N-${raw.slice(0, 4).toUpperCase()}`;
}

export function avatarColor(key: string): string {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

export function avatarInitial(label: string): string {
  const t = label.trim();
  if (!t) return 'A';
  return (Array.from(t)[0] || 'A').toUpperCase();
}

export function wsNodeTags(item: KanbanItem, status?: string): string[] {
  if (item.tags?.length) return item.tags.slice(0, 4);
  const tags: string[] = [];
  const blob = `${item.title} ${item.description || ''}`;
  const rules: Array<[string, RegExp]> = [
    ['API', /api|sse|endpoint|協議/i],
    ['Schema', /schema|資料結構|npc|quest/i],
    ['Design', /設計|design|架構|選型/i],
    ['Database', /資料庫|postgres|sql/i],
    ['Code', /程式|code|實作|typescript|python/i],
  ];
  for (const [label, re] of rules) {
    if (re.test(blob)) tags.push(label);
  }
  if (!tags.length && status) tags.push(status.replace(/_/g, ' '));
  return tags.slice(0, 3);
}

export function wsNodeProgress(item: KanbanItem, status: string): number {
  if (typeof item.progress === 'number' && item.progress >= 0 && item.progress <= 100) {
    return item.progress;
  }
  return STATUS_PROGRESS[status] ?? 0;
}
