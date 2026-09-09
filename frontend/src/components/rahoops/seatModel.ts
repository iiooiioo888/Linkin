/**
 * 席位投遞監察頁的共用資料模型（僅供 rahoops/ 內部使用）。
 * kind 中文標籤在此定義，勿回寫 rahoUi.ts（那份是質詢事件詞彙表）。
 */
import type { SeatIOFeedRow } from '../../types';
import { rahoLayerOf } from '../../lib/rahoUi';

export const SEAT_KIND_LABELS: Record<string, string> = {
  decompose: '任務分解',
  execute: '執行',
  rework: '退回重做',
  review: '審查',
  synthesize: '整合',
  final_review: '最終審查',
  inspect: '憲兵裁決',
};

export const SEAT_KIND_TONE: Record<string, string> = {
  decompose: 'var(--apple-blue)',
  execute: 'var(--apple-label)',
  rework: 'var(--apple-orange)',
  review: '#BF5AF2',
  synthesize: 'var(--apple-blue)',
  final_review: '#BF5AF2',
  inspect: 'var(--apple-red)',
};

export function seatKindLabel(kind?: string | null): string {
  const key = kind || '';
  return SEAT_KIND_LABELS[key] || key || '投遞';
}

export function seatKindTone(kind?: string | null): string {
  return SEAT_KIND_TONE[kind || ''] || 'var(--apple-secondary)';
}

/** context_sources 的來源性質分類（決定色點），與 backend/company/orchestrator.py 的 kind 對齊 */
export const SOURCE_TONE: Record<string, string> = {
  system: 'var(--apple-gray)',
  org_chart: 'var(--apple-gray)',
  role_brief: 'var(--apple-blue)',
  role_prompt: 'var(--apple-blue)',
  role_memory: '#BF5AF2',
  dependency: 'var(--apple-green)',
  artifacts: 'var(--apple-green)',
  deliverable: 'var(--apple-green)',
  task_brief: 'var(--apple-orange)',
  campaign: 'var(--apple-orange)',
  template: 'var(--apple-gray)',
  tools: 'var(--apple-blue)',
  preflight_ruling: 'var(--apple-red)',
  grill_ruling: 'var(--apple-red)',
  review_feedback: 'var(--apple-red)',
  constitution: '#BF5AF2',
  stats: 'var(--apple-gray)',
  unknown: 'var(--apple-gray)',
};

export function sourceTone(kind?: string | null): string {
  return SOURCE_TONE[kind || 'unknown'] || 'var(--apple-gray)';
}

export interface SeatAgg {
  role: string;
  role_label: string;
  layer: number | null;
  lane: string;
  count: number;
  cost: number;
  last_ts: string;
  degraded: number;
  errors: number;
  kinds: Record<string, number>;
}

function laneOf(row: SeatIOFeedRow, layer: number | null): string {
  if (row.lane) return row.lane;
  if (layer === 0) return 'kernel';
  if (layer === 1) return 'inspect';
  return 'command';
}

/** 依 role 聚合 feed items，供左欄席位名冊使用 */
export function aggregateSeats(rows: SeatIOFeedRow[]): SeatAgg[] {
  const map = new Map<string, SeatAgg>();
  for (const row of rows) {
    const roleId = row.role || 'unknown';
    const layer = row.layer ?? rahoLayerOf(roleId, null);
    let agg = map.get(roleId);
    if (!agg) {
      agg = {
        role: roleId,
        role_label: row.role_label || roleId,
        layer,
        lane: laneOf(row, layer),
        count: 0,
        cost: 0,
        last_ts: '',
        degraded: 0,
        errors: 0,
        kinds: {},
      };
      map.set(roleId, agg);
    }
    agg.count += 1;
    agg.cost += Number(row.cost_usd) || 0;
    if (!agg.last_ts || String(row.ts) > String(agg.last_ts)) agg.last_ts = String(row.ts || '');
    if (!agg.role_label || agg.role_label === agg.role) agg.role_label = row.role_label || roleId;
    if (agg.layer == null && row.layer != null) agg.layer = row.layer;
    if (row.degraded) agg.degraded += 1;
    if (row.error) agg.errors += 1;
    agg.kinds[row.kind] = (agg.kinds[row.kind] || 0) + 1;
  }
  return [...map.values()].sort(
    (a, b) => b.count - a.count || b.cost - a.cost || a.role.localeCompare(b.role),
  );
}

export interface FeedTotals {
  count: number;
  roles: number;
  cost: number;
  degraded: number;
  errors: number;
  items: number;
}

export function feedTotals(rows: SeatIOFeedRow[], totalRoles: number): FeedTotals {
  const roles = new Set<string>();
  const workItems = new Set<string>();
  let cost = 0;
  let degraded = 0;
  let errors = 0;
  for (const row of rows) {
    if (row.role) roles.add(row.role);
    if (row.item_id) workItems.add(row.item_id);
    cost += Number(row.cost_usd) || 0;
    if (row.degraded) degraded += 1;
    if (row.error) errors += 1;
  }
  return {
    count: rows.length,
    roles: totalRoles || roles.size,
    cost,
    degraded,
    errors,
    items: workItems.size,
  };
}

/** 同一次投遞的重試／工具閉環序標：#attempt·step 或 #attempt·step/tool_steps */
export function attemptTag(row: Pick<SeatIOFeedRow, 'attempt' | 'step' | 'tool_steps'>): string {
  const a = Number(row.attempt) || 0;
  const s = Number(row.step) || 0;
  const t = Number(row.tool_steps) || 0;
  if (!a && !s) return '';
  const den = Math.max(t, s);
  return den > s ? `#${a || 1}·${s}/${den}` : `#${a || 1}·${s}`;
}

export function fmtChars(n: number | null | undefined): string {
  const v = Number(n) || 0;
  if (v >= 10000) return `${(v / 1000).toFixed(1)}k`;
  return String(v);
}

export function fmtDuration(ms: number | null | undefined): string {
  const v = Number(ms) || 0;
  if (!v) return '—';
  if (v < 1000) return `${v}ms`;
  return `${(v / 1000).toFixed(1)}s`;
}

/** feed 的單行可能缺少欄位，統一以時間新→舊排序 */
export function normalizeRows(raw: SeatIOFeedRow[] | undefined | null): SeatIOFeedRow[] {
  return (raw ?? []).slice().sort((a, b) => String(b.ts).localeCompare(String(a.ts)));
}
