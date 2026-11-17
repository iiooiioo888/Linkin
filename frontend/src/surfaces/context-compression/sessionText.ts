/**
 * 把本機會話編成可送去規則壓縮的正文。只讀既有 storage，不另建對話庫。
 */
import { loadActiveSessionId, loadSessions } from '../../lib/storage';
import type { ChatMessage, ChatSession } from '../../types';

export function formatConversation(messages: ChatMessage[]): string {
  return messages
    .map((message) => {
      const content = message.content.trim();
      if (!content) return '';
      const label = message.role === 'user' ? '你' : '回應';
      return `${label}：${content}`;
    })
    .filter((line) => line.length > 0)
    .join('\n\n');
}

export function activeConversationText(
  sessions: ChatSession[] = loadSessions(),
  activeId: string | null = loadActiveSessionId(),
): string {
  const session =
    (activeId ? sessions.find((item) => item.id === activeId) : undefined) ?? sessions[0];
  if (!session) return '';
  return formatConversation(session.messages);
}
