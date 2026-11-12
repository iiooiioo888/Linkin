/**
 * 訊息層級任務視圖：live 監控判斷、互動狀態與 Context 綁定 taskId 解析。
 */
import type { ChatMessage } from '../../types';
import { isRunningTaskStatus, TERMINAL_TASK_STATUSES } from './status';

export function hasUnresolvedDecision(message: Pick<ChatMessage, 'taskState'>): boolean {
  return (message.taskState?.raho?.pending_decisions ?? []).some(
    (p) => !p.resolved && (p.choices?.length ?? 0) > 0,
  );
}

/** Grill 質詢尚未鎖定、未終止 → 仍算互動中 */
export function isGrillInteractive(message: Pick<ChatMessage, 'grill'>): boolean {
  const g = message.grill;
  return Boolean(g && !g.locked && !g.terminated);
}

/** L3 戰術地圖等待 L5 裁決 */
export function isBattleWaiting(message: Pick<ChatMessage, 'battle'>): boolean {
  const b = message.battle;
  return b?.status === 'ESCALATE_TO_USER' && Boolean(b.waiting_for_user_decision);
}

/**
 * 僅在任務仍 live／互動中時切右側監控欄。
 * 已完成／失敗／取消的歷史任務不切欄；寒暄 SSE、無任務的簡單對話亦不切欄。
 */
export function isLiveMonitorTask(
  message: Pick<ChatMessage, 'taskState' | 'taskId' | 'grill' | 'battle' | 'streaming'>,
): boolean {
  if (isGrillInteractive(message) || isBattleWaiting(message)) return true;
  if (hasUnresolvedDecision(message)) return true;

  const task = message.taskState;
  if (task) {
    if (task.status === 'awaiting_confirmation') return true;
    if (isRunningTaskStatus(task.status)) return true;
    if (task.status === 'failed' || task.status === 'interrupted') return true;
    if (TERMINAL_TASK_STATUSES.has(task.status)) return false;
  }

  // 僅 taskId、尚無快照：任務剛建立、串流中才暫開監控
  if (message.taskId && !task) return Boolean(message.streaming);

  return false;
}

export function activeTaskMessage<T extends Pick<ChatMessage, 'taskState' | 'taskId'>>(
  messages: T[],
): T | null {
  return [...messages].reverse().find(isLiveMonitorTask) ?? null;
}

/** 進行中任務（不含失敗／已完成）— 用於精簡管線條。 */
export function runningTaskMessage<
  T extends Pick<ChatMessage, 'taskState' | 'taskId' | 'streaming'>,
>(messages: T[]): T | null {
  return (
    [...messages].reverse().find((m) => {
      const st = m.taskState?.status;
      if (st === 'running' || st === 'pending') return true;
      if (m.taskId && !m.taskState && m.streaming) return true;
      return false;
    }) ?? null
  );
}

/**
 * 解析 Context 面板應綁定的任務 ID（對話詳細區用）。
 *
 * **契約（對話頁 C-UI-004）**：
 * - 僅在本會話 `messages` 內解析；永遠綁定「進行中 → 否則最近一則」
 * - `prefer` 僅當屬於本會話才生效；外來／其他對話 ID **一律忽略**
 * - 不回落全域最新軌跡；UI 不得提供跨對話任務選擇器
 */
export function resolveContextTaskId(
  messages: Array<Pick<ChatMessage, 'taskState' | 'taskId'>>,
  prefer?: string | null,
): string | null {
  const sessionIds = new Set<string>();
  for (const m of messages) {
    const id = (m.taskId || m.taskState?.task_id || '').trim();
    if (id) sessionIds.add(id);
  }
  const explicit = (prefer || '').trim();
  // 僅當 prefer 確屬本會話才採用；外來 ID 一律忽略
  if (explicit && sessionIds.has(explicit)) return explicit;
  const live = activeTaskMessage(messages);
  const fromLive = (live?.taskId || live?.taskState?.task_id || '').trim();
  if (fromLive) return fromLive;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    const id = (m.taskId || m.taskState?.task_id || '').trim();
    if (id) return id;
  }
  return null;
}
