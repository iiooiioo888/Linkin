/**
 * 任務耗時與預計剩餘時間（ETA）— 純前端估算，資料源為 task.created_at 與
 * phase_change 事件流（後端已帶 Unix 秒 ts），不需新增 API。
 *
 * 估算策略：
 *  - 已耗時：created_at → 現在；終態任務用最後事件時間封頂。
 *  - 分段：連續 phase_change 切出每段時長；同一階段多次出現取均值。
 *  - ETA：當前階段（均值 − 本段已耗）＋ 未經歷階段（用已見段時長中位數）；
 *    公司模式 execute_review 依看板完成比例細分；反思閉環按剩餘迭代輪數加權。
 *  - 樣本不足（第一個階段還沒走完）→ 回傳 null，UI 顯示「估算中」。
 */
import { useEffect, useState } from 'react';
import type { KanbanItem, TaskEvent, TaskProgress } from '../types';

/** 每秒 tick（僅執行中需要，避免定時器常開）。 */
export function useNowTick(active: boolean, intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [active, intervalMs]);
  return now;
}

export function formatDuration(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  if (s < 60) return `${s} 秒`;
  const m = Math.floor(s / 60);
  if (m < 60) return s % 60 ? `${m} 分 ${s % 60} 秒` : `${m} 分鐘`;
  const h = Math.floor(m / 60);
  return `${h} 小時 ${m % 60} 分`;
}

/** 緊湊耗時：5m 36s */
export function formatDurationCompact(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return s % 60 ? `${m}m ${s % 60}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

/** 事件絕對時間戳 HH:MM:SS。 */
export function eventClock(ts: number): string {
  const d = new Date(ts * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
}

/** 任務最後一個事件時間（終態任务的結束時刻近似）。 */
export function lastEventTsOf(task: TaskProgress): number {
  const evs = task.events ?? [];
  if (evs.length) return evs[evs.length - 1].ts;
  return typeof task.created_at === 'number' ? task.created_at : 0;
}

interface Segment {
  phase: string;
  start: number;
  end: number;
}

function finishedStatus(task: TaskProgress): boolean {
  return !['running', 'pending'].includes(task.status);
}

/** created_at 缺省時退回最早事件。 */
function taskStartTs(task: TaskProgress): number | null {
  if (typeof task.created_at === 'number' && task.created_at > 0) return task.created_at;
  const first = (task.events ?? [])[0];
  return first ? first.ts : null;
}

function lastEventTs(task: TaskProgress): number {
  const evs = task.events ?? [];
  return evs.length ? evs[evs.length - 1].ts : taskStartTs(task) ?? 0;
}

/** 由 phase_change 事件切段；末段補到「現在（或結束）」。 */
export function phaseSegments(task: TaskProgress, nowMs: number): Segment[] {
  const start = taskStartTs(task);
  if (start == null) return [];
  const changes: TaskEvent[] = (task.events ?? []).filter(
    (e) => e.event === 'phase_change' || (task.resolved_path === 'company' && e.event === 'phase'),
  );
  const segs: Segment[] = [];
  const finish = finishedStatus(task) ? lastEventTs(task) : nowMs / 1000;
  let curPhase = changes.length ? String(changes[0].data?.phase ?? task.phase ?? '') : task.phase || '';
  let curStart = changes.length ? Math.max(start, changes[0].ts) : start;
  for (let i = 1; i < changes.length; i++) {
    const ph = String(changes[i].data?.phase ?? '');
    if (!ph || ph === curPhase) continue;
    if (curPhase && changes[i].ts > curStart) segs.push({ phase: curPhase, start: curStart, end: changes[i].ts });
    curPhase = ph;
    curStart = changes[i].ts;
  }
  const end = Math.max(curStart, finish);
  if (curPhase) segs.push({ phase: curPhase, start: curStart, end });
  return segs;
}

function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

function mean(xs: number[]): number | null {
  if (!xs.length) return null;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

function kanbanCounts(task: TaskProgress): { done: number; total: number } {
  const kanban = task.kanban ?? {};
  let total = 0;
  for (const items of Object.values(kanban)) total += (items as KanbanItem[]).length;
  return { done: (kanban.done ?? []).length, total };
}

export interface EtaInfo {
  /** 總已耗秒（執行中＝now−start；終態＝end−start） */
  elapsedSec: number;
  /** 預計剩餘秒；null=樣本不足 */
  remainingSec: number | null;
  /** 預計總時長（elapsed+remaining） */
  totalSec: number | null;
  /** 當前階段已耗秒 */
  curPhaseSec: number | null;
  /** 估算依據，tooltip 用 */
  method: 'phase' | 'items' | 'loops+phase' | 'insufficient' | 'finished';
  /** 各階段名 → 平均秒（已完成段統計） */
  phaseAvg: Record<string, number>;
}

const DEFAULT_MAX_ITERATIONS = 3;

export function taskEta(task: TaskProgress, nowMs: number): EtaInfo | null {
  const start = taskStartTs(task);
  if (start == null) return null;
  const done = finishedStatus(task);
  const elapsedSec = Math.max(0, (done ? lastEventTs(task) : nowMs / 1000) - start);
  const segs = phaseSegments(task, nowMs);
  const byPhase = new Map<string, number[]>();
  for (const sg of segs) {
    if (!byPhase.has(sg.phase)) byPhase.set(sg.phase, []);
    byPhase.get(sg.phase)!.push(sg.end - sg.start);
  }
  // 最後一段若任務已終態則其長度可信；執行中最後一段是「當前階段已耗」
  const completeSegs = done ? segs : segs.slice(0, -1);
  const cByPhase = new Map<string, number[]>();
  for (const sg of completeSegs) {
    if (!cByPhase.has(sg.phase)) cByPhase.set(sg.phase, []);
    cByPhase.get(sg.phase)!.push(Math.max(1, sg.end - sg.start));
  }
  const phaseAvg: Record<string, number> = {};
  for (const [k, v] of cByPhase) phaseAvg[k] = mean(v) ?? 0;

  if (done) {
    return {
      elapsedSec, remainingSec: null, totalSec: elapsedSec, curPhaseSec: null,
      method: 'finished', phaseAvg,
    };
  }

  const curSeg = segs[segs.length - 1];
  const curPhaseSec = curSeg ? Math.max(0, nowMs / 1000 - curSeg.start) : null;
  const curPhase = task.phase || curSeg?.phase || '';
  const allDurs = completeSegs.map((s) => Math.max(1, s.end - s.start));
  const med = median(allDurs);

  let remaining = 0;
  let method: EtaInfo['method'] = 'phase';
  let contributed = false;

  // 1) 當前階段剩餘
  if (curPhase === 'execute_review') {
    const { done: dn, total } = kanbanCounts(task);
    if (total > 0 && dn > 0 && curPhaseSec != null && curPhaseSec > 3) {
      remaining += dn >= total ? 0 : (curPhaseSec / dn) * (total - dn);
      method = 'items';
      contributed = true;
    }
  } else {
    const est = phaseAvg[curPhase] ?? med;
    if (est != null && curPhaseSec != null) {
      remaining += Math.max(est * 0.15, est - curPhaseSec); // 不低於均值 15%
      contributed = true;
    }
  }

  // 2) 未經歷階段（階段清單裡尚未出現的）
  const known = new Set(segs.map((s) => s.phase));
  const unseenEst = med;
  if (unseenEst != null) {
    const isCompany = task.resolved_path === 'company';
    const isOPC = task.resolved_path === 'opc';
    const list = isCompany
      ? ['campaign_plan', 'decompose', 'execute_review', 'synthesize', 'final_review', 'evaluate', 'done']
      : isOPC
        ? ['sense_opc', 'preprocess_opc', 'analyze_opc', 'diagnose_opc', 'decide_opc', 'act_opc', 'done']
        : ['done'];
    const pendingPhases = list.filter((p) => p !== 'done' && !known.has(p) && p !== curPhase);
    remaining += pendingPhases.length * unseenEst;
    if (pendingPhases.length) contributed = true;
  }

  // 3) 反思閉環：剩餘迭代輪（improve+evaluate 循環）
  if (!done && (task.resolved_path === '' || task.resolved_path === 'simple')) {
    const improveSegs = cByPhase.get('improve') ?? [];
    const maxIter = Number(task.options?.max_iterations) || DEFAULT_MAX_ITERATIONS;
    const loopsLeft = Math.max(0, maxIter - 1 - improveSegs.length);
    if (loopsLeft > 0 && phaseAvg.improve != null && phaseAvg.evaluate != null) {
      remaining += loopsLeft * (phaseAvg.improve + phaseAvg.evaluate);
      method = 'loops+phase';
      contributed = true;
    }
  }

  // 4) 公司模式收尾階段（synthesize/final_review/evaluate）若當前在 execute_review，用均值估
  if (method === 'items' && med != null) {
    remaining += 2 * med; // synthesize + final_review 粗估
  }

  if (!contributed || remaining <= 0) {
    return {
      elapsedSec, remainingSec: null, totalSec: null, curPhaseSec,
      method: 'insufficient', phaseAvg,
    };
  }
  return {
    elapsedSec,
    remainingSec: remaining,
    totalSec: elapsedSec + remaining,
    curPhaseSec,
    method,
    phaseAvg,
  };
}
