/**
 * 歷史對話只讀既有會話庫（localStorage 的 loadSessions／saveActiveSessionId）。
 * 不另建儲存，也不另行送出聊天。
 */
import { hashForSurface } from '../../routes/catalog';
import type { ChatMessage, ChatSession } from '../../types';
import {
  loadActiveSessionId,
  loadSessions,
  saveActiveSessionId,
} from '../../lib/storage';

/** 殼層的對話入口。繼續與空狀態都回到這一頁。 */
export const CONVERSATION_HASH = hashForSurface('chat');

const PREVIEW_LIMIT = 80;

export interface SessionStore {
  load(): ChatSession[];
  loadActiveId(): string | null;
  saveActiveId(id: string): void;
}

export const browserSessionStore: SessionStore = {
  load: loadSessions,
  loadActiveId: loadActiveSessionId,
  saveActiveId: saveActiveSessionId,
};

export interface HistoryRow {
  id: string;
  title: string;
  updatedAt: number;
  when: string;
  preview: string;
  messageCount: number;
  active: boolean;
}

export interface HistoryTurn {
  id: string;
  role: 'user' | 'assistant';
  label: string;
  content: string;
  when: string;
}

export interface OpenedHistory {
  id: string;
  title: string;
  when: string;
  messageCount: number;
  active: boolean;
  turns: HistoryTurn[];
}

export function sessionTitle(title: string): string {
  const trimmed = title.trim();
  return trimmed || '新對話';
}

export function formatHistoryWhen(ts: number, now = Date.now()): string {
  const diff = Math.max(0, now - ts);
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return '剛剛';
  if (minutes < 60) return `${minutes} 分鐘前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小時前`;
  return new Date(ts).toLocaleDateString('zh-TW');
}

function visibleMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages.filter((message) => message.content.trim().length > 0);
}

export function previewText(messages: ChatMessage[]): string {
  const visible = visibleMessages(messages);
  const last = visible[visible.length - 1];
  if (!last) return '沒有內容';
  const text = last.content.replace(/\s+/g, ' ').trim();
  if (text.length <= PREVIEW_LIMIT) return text;
  return `${text.slice(0, PREVIEW_LIMIT)}…`;
}

export function roleLabel(role: 'user' | 'assistant'): string {
  return role === 'user' ? '你' : '回應';
}

export function listHistory(store: SessionStore, now = Date.now()): HistoryRow[] {
  const activeId = store.loadActiveId();
  return [...store.load()]
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .map((session) => {
      const messages = visibleMessages(session.messages);
      return {
        id: session.id,
        title: sessionTitle(session.title),
        updatedAt: session.updatedAt,
        when: formatHistoryWhen(session.updatedAt, now),
        preview: previewText(session.messages),
        messageCount: messages.length,
        active: session.id === activeId,
      };
    });
}

export function openHistory(store: SessionStore, id: string, now = Date.now()): OpenedHistory | null {
  const session = store.load().find((item) => item.id === id);
  if (!session) return null;
  const messages = visibleMessages(session.messages);
  return {
    id: session.id,
    title: sessionTitle(session.title),
    when: formatHistoryWhen(session.updatedAt, now),
    messageCount: messages.length,
    active: store.loadActiveId() === session.id,
    turns: messages.map((message) => ({
      id: message.id,
      role: message.role,
      label: roleLabel(message.role),
      content: message.content.trim(),
      when: formatHistoryWhen(message.timestamp, now),
    })),
  };
}

/** 把既有會話設為作用中，並交回對話頁。找不到則不寫入。 */
export function resumeHistory(
  store: SessionStore,
  id: string,
): { id: string; hash: string } | null {
  const exists = store.load().some((item) => item.id === id);
  if (!exists) return null;
  store.saveActiveId(id);
  return { id, hash: CONVERSATION_HASH };
}
