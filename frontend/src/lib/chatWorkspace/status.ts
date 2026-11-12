/**
 * 任務狀態集合與終止狀態 helpers。
 */
import type { TaskProgress } from '../../types';

export const TERMINAL_TASK_STATUSES = new Set<TaskProgress['status']>([
  'completed',
  'failed',
  'cancelled',
  'interrupted',
  'rejected',
  'expired',
]);

const KNOWN_TASK_STATUSES = new Set<TaskProgress['status']>([
  'pending',
  'running',
  'awaiting_confirmation',
  ...TERMINAL_TASK_STATUSES,
]);

export function isRunningTaskStatus(status: TaskProgress['status'] | undefined): boolean {
  return status === 'running' || status === 'pending';
}

export function isTerminalTaskStatus(status: TaskProgress['status'] | undefined): boolean {
  return status != null && TERMINAL_TASK_STATUSES.has(status);
}

/** WebSocket task_finished 等路徑：僅接受已知狀態，避免 cancelled 被誤落成 completed。 */
export function coerceTaskProgressStatus(
  value: unknown,
  fallback: TaskProgress['status'] = 'completed',
): TaskProgress['status'] {
  if (typeof value === 'string' && KNOWN_TASK_STATUSES.has(value as TaskProgress['status'])) {
    return value as TaskProgress['status'];
  }
  return fallback;
}

/** 後端拒絕重複取消時的錯誤文案（任務已終止）。 */
export function isTaskAlreadyEndedError(message: string): boolean {
  const m = message.trim();
  return /任務已結束|無法取消|already (ended|cancelled)/i.test(m);
}
