/** 多會話 localStorage 持久化（補償後端無 /history 端點）。 */
import type { ChatSession } from '../types';
import { uuidv4 } from './uuid';

const SESSIONS_KEY = 'evoloop_sessions';
const ACTIVE_KEY = 'evoloop_active_session';
const MAX_SESSIONS = 50;

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

export function saveSessions(sessions: ChatSession[]): void {
  try {
    localStorage.setItem(
      SESSIONS_KEY,
      JSON.stringify(sessions.slice(0, MAX_SESSIONS)),
    );
  } catch {
    // 儲存空間不足時靜默忽略
  }
}

export function loadActiveSessionId(): string | null {
  return localStorage.getItem(ACTIVE_KEY);
}

export function saveActiveSessionId(id: string): void {
  localStorage.setItem(ACTIVE_KEY, id);
}

export function newSessionId(): string {
  return uuidv4().replace(/-/g, '');
}
