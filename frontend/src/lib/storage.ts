/** 多會話 localStorage 持久化（補償後端無 /history 端點）。 */
import type { ChatSession, KanbanItem, TaskProgress } from '../types';

const SESSIONS_KEY = 'evoloop_sessions';
const ACTIVE_KEY = 'evoloop_active_session';
const MAX_SESSIONS = 50;
/** 降級快檔時保留的看板正文／思考／事件長度（公司模式單項 output 可達 20000 字） */
const SLIM_OUTPUT = 1500;
const SLIM_THINKING = 800;
const SLIM_EVENTS = 25;
/** 二度降級時保留的會話數 */
const SLIM_SESSIONS = 10;

export function loadSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(SESSIONS_KEY);
    if (!raw) return [];
    const sessions = JSON.parse(raw) as ChatSession[];
    // 依更新時間新→舊排序
    return sessions.sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

function slimTaskState(task: TaskProgress): TaskProgress {
  const kanban: Record<string, KanbanItem[]> = {};
  for (const [status, items] of Object.entries(task.kanban ?? {})) {
    kanban[status] = items.map((item) => ({
      ...item,
      output: item.output ? item.output.slice(0, SLIM_OUTPUT) : item.output,
      thinking: item.thinking ? item.thinking.slice(0, SLIM_THINKING) : item.thinking,
    }));
  }
  return {
    ...task,
    kanban,
    events: (task.events ?? []).slice(-SLIM_EVENTS),
  };
}

function slimSessions(sessions: ChatSession[]): ChatSession[] {
  return sessions.map((session) => ({
    ...session,
    messages: session.messages.map((message) =>
      message.taskState ? { ...message, taskState: slimTaskState(message.taskState) } : message,
    ),
  }));
}

/**
 * 寫入 localStorage。
 *
 * 昔日實作把配額異常靜默吞掉 —— 結果是整個會話歷史悄悄停止持久化，
 * 使用者要到重載頁面才發現全沒了。改成逐級降級重試，盡可能留住東西。
 */
export function saveSessions(sessions: ChatSession[]): void {
  const trimmed = sessions.slice(0, MAX_SESSIONS);
  const attempts: Array<() => string> = [
    () => JSON.stringify(trimmed),
    () => JSON.stringify(slimSessions(trimmed)),
    () => JSON.stringify(slimSessions(trimmed.slice(0, SLIM_SESSIONS))),
  ];
  for (const attempt of attempts) {
    try {
      localStorage.setItem(SESSIONS_KEY, attempt());
      return;
    } catch {
      // 換下一級降級方案
    }
  }
}

export function loadActiveSessionId(): string | null {
  return localStorage.getItem(ACTIVE_KEY);
}

export function saveActiveSessionId(id: string): void {
  localStorage.setItem(ACTIVE_KEY, id);
}

export function newSessionId(): string {
  return crypto.randomUUID().replace(/-/g, '');
}
