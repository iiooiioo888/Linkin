/**
 * 監控視覺元件資料衍生 — 從既有 API／store 彙總，無序列時回傳空陣列。
 */
import type { AgentEvent, OptimizationMonitorData, RoleAgent, TaskSummary } from '../types';

export type HeatmapCell = { level: 0 | 1 | 2 | 3 | 4; error?: boolean };

/** 7 行（週）× N 列（時）活動熱力圖 — 由任務 created_at 或事件 ts 衍生 */
export function buildActivityHeatmap(
  tasks: TaskSummary[],
  events: AgentEvent[] = [],
  cols = 24,
): HeatmapCell[][] {
  const now = Date.now();
  const grid: HeatmapCell[][] = Array.from({ length: 7 }, () =>
    Array.from({ length: cols }, () => ({ level: 0 as const })),
  );

  const bump = (ts: number, failed = false) => {
    const ageH = (now - ts * 1000) / 3600000;
    if (ageH < 0 || ageH >= 7 * cols) return;
    const row = Math.min(6, Math.floor(ageH / cols));
    const col = Math.floor(ageH % cols);
    const cell = grid[6 - row][col];
    if (failed) {
      cell.error = true;
      cell.level = 4;
      return;
    }
    const next = Math.min(4, cell.level + 1);
    cell.level = next as 0 | 1 | 2 | 3 | 4;
  };

  tasks.forEach((t) => bump(t.created_at, t.status === 'failed'));
  events.forEach((e) => {
    if (e.ts == null) return;
    const ts = typeof e.ts === 'number' ? e.ts : Math.floor(Date.parse(e.ts) / 1000);
    if (!Number.isFinite(ts)) return;
    bump(ts, e.event.includes('error') || e.event.includes('fail'));
  });

  return grid;
}

export type MatrixCell = { count: number; tone: 'green' | 'blue' | 'gold' | 'red' | 'purple' | 'dim' };

const LAYER_ROWS = [
  { key: 'L4', label: 'L4', match: (t: TaskSummary) => t.resolved_path === 'company' && /audit|requirement/i.test(t.phase) },
  { key: 'L3', label: 'L3', match: (t: TaskSummary) => t.resolved_path === 'company' && /tactical|command/i.test(t.phase) },
  { key: 'L2', label: 'L2', match: (t: TaskSummary) => t.resolved_path === 'company' || t.resolved_path === 'opc' },
];

/** L4/L3/L2 × 24 小時任務分佈矩陣 */
export function buildTaskDistributionMatrix(tasks: TaskSummary[]): MatrixCell[][] {
  const now = new Date();
  const hour = now.getHours();

  return LAYER_ROWS.map((row) => {
    const rowTasks = tasks.filter(row.match);
    return Array.from({ length: 24 }, (_, h) => {
      const inHour = rowTasks.filter((t) => {
        const d = new Date(t.created_at * 1000);
        return d.getHours() === h && d.getDate() === now.getDate();
      });
      const count = inHour.length;
      let tone: MatrixCell['tone'] = 'dim';
      if (count > 0) {
        const failed = inHour.some((t) => t.status === 'failed');
        const running = inHour.some((t) => t.status === 'running');
        if (failed) tone = 'red';
        else if (running) tone = 'blue';
        else if (h === hour) tone = 'gold';
        else tone = 'green';
      }
      return { count, tone };
    });
  });
}

export function matrixToneColor(tone: MatrixCell['tone']): string {
  const map: Record<MatrixCell['tone'], string> = {
    green: 'var(--console-green)',
    blue: 'var(--console-blue)',
    gold: 'var(--console-accent)',
    red: 'var(--console-danger)',
    purple: 'var(--console-purple)',
    dim: 'var(--console-dim)',
  };
  return map[tone];
}

/** 24 點 spark 序列 — 由反思週期或任務計數衍生 */
export function buildSparkSeries24(
  data: OptimizationMonitorData | null,
  tasks: TaskSummary[],
): number[] {
  const cycles = data?.reflection_trace?.recent_cycles ?? [];
  if (cycles.length >= 3) {
    const base = cycles.map((c) => c.iterations ?? 1);
    while (base.length < 24) base.unshift(base[0] ?? 0);
    return base.slice(-24);
  }
  const buckets = Array(24).fill(0);
  tasks.forEach((t) => {
    const h = new Date(t.created_at * 1000).getHours();
    buckets[h] += 1;
  });
  return buckets;
}

export type StackSegment = { label: string; value: number; color: string };

export function buildStatusStack(stats: {
  tasks_running?: number;
  tasks_completed?: number;
  tasks_failed?: number;
  tasks_total?: number;
}): StackSegment[] {
  const running = stats.tasks_running ?? 0;
  const done = stats.tasks_completed ?? 0;
  const failed = stats.tasks_failed ?? 0;
  const total = stats.tasks_total ?? running + done + failed;
  const queue = Math.max(0, total - running - done - failed);
  return [
    { label: '執行', value: running, color: 'var(--console-blue)' },
    { label: '完成', value: done, color: 'var(--console-green)' },
    { label: '失敗', value: failed, color: 'var(--console-danger)' },
    { label: '隊列', value: queue, color: 'var(--console-dim)' },
  ].filter((s) => s.value > 0);
}

export function agentResourceGauges(agent: RoleAgent): Array<{ label: string; pct: number; color: string }> {
  const m = agent.metrics;
  const capPct = Math.round(m?.capacity_pct ?? (agent.capacity_used ?? 0) * 100);
  const memPct = Math.min(100, Math.round(((m?.tokens_in ?? 0) + (m?.tokens_out ?? 0)) / 1000));
  const netPct = Math.min(100, Math.round((m?.tool_calls ?? 0) * 5));
  return [
    { label: 'CPU', pct: capPct, color: 'var(--console-blue)' },
    { label: 'MEM', pct: memPct, color: 'var(--console-green)' },
    { label: 'NET', pct: netPct, color: 'var(--console-cyan)' },
  ];
}

export function taskPriority(task: TaskSummary): 'p1' | 'p2' | 'p3' {
  if (task.status === 'failed' || task.status === 'cancelled') return 'p1';
  if (task.status === 'running' || task.status === 'pending') return 'p2';
  return 'p3';
}

const SKILL_COLORS = [
  'var(--console-green)',
  'var(--console-blue)',
  'var(--console-accent)',
  'var(--console-purple)',
  'var(--console-cyan)',
  'var(--console-danger)',
];

export function skillTagColor(index: number): string {
  return SKILL_COLORS[index % SKILL_COLORS.length];
}
