import { describe, expect, it } from 'vitest';
import type { ChatSession } from '../../types';
import { activeConversationText, formatConversation } from './sessionText';

const now = 1_700_000_000_000;

function session(partial: Partial<ChatSession> & Pick<ChatSession, 'id'>): ChatSession {
  return {
    title: '標題',
    createdAt: now,
    updatedAt: now,
    messages: [],
    ...partial,
  };
}

describe('context compression session text', () => {
  it('drops blank turns and labels the speakers', () => {
    expect(
      formatConversation([
        { id: 'u', role: 'user', content: '  壓力偏高  ', timestamp: now },
        { id: 'blank', role: 'assistant', content: '   ', timestamp: now },
        { id: 'a', role: 'assistant', content: '先看汽包。', timestamp: now },
      ]),
    ).toBe('你：壓力偏高\n\n回應：先看汽包。');
  });

  it('prefers the active session', () => {
    const sessions = [
      session({
        id: 'other',
        messages: [{ id: 'm', role: 'user', content: '別的對話', timestamp: now }],
      }),
      session({
        id: 'active',
        messages: [{ id: 'm', role: 'user', content: '這一筆', timestamp: now }],
      }),
    ];
    expect(activeConversationText(sessions, 'active')).toBe('你：這一筆');
    expect(activeConversationText(sessions, 'missing')).toBe('你：別的對話');
    expect(activeConversationText([], null)).toBe('');
  });
});
