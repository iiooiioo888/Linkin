/**
 * 任務預算與 Token 估算。
 */
import type { TaskProgress } from '../../types';
import { flattenWsNodes } from './kanban';

export function numBudget(task: TaskProgress | null | undefined, key: string): number {
  const v = task?.budget?.[key];
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

export function wsTokens(task: TaskProgress | null | undefined): number {
  const total = numBudget(task, 'tokens_total');
  if (total > 0) return total;
  const sum = numBudget(task, 'tokens_in') + numBudget(task, 'tokens_out');
  if (sum > 0) return sum;
  const fromNodes = flattenWsNodes(task).reduce((acc, n) => acc + (n.item.tokens || 0), 0);
  if (fromNodes > 0) return fromNodes;
  return (task?.events ?? []).length * 180;
}
