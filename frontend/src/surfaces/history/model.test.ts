import { describe, expect, it } from 'vitest';
import { buildAppRouteHash, getDefaultRoute } from '../../lib/appRoute';
import { loadActiveSessionId, loadSessions, saveActiveSessionId } from '../../lib/storage';
import type { ChatSession } from '../../types';
import {
  browserSessionStore,
  CONVERSATION_HASH,
  formatHistoryWhen,
  listHistory,
  openHistory,
  previewText,
  resumeHistory,
  sessionTitle,
  type SessionStore,
} from './model';

const now = 1_700_000_000_000;

function session(partial: Partial<ChatSession> & Pick<ChatSession, 'id'>): ChatSession {
  return {
    title: '標題',
    createdAt: now - 10_000,
    updatedAt: now - 5_000,
    messages: [],
    ...partial,
  };
}

function memoryStore(sessions: ChatSession[], active: string | null = null): SessionStore & {
  activeId: () => string | null;
  writes: () => number;
} {
  let activeId = active;
  let writes = 0;
  return {
    load: () => sessions,
    loadActiveId: () => activeId,
    saveActiveId: (id: string) => {
      writes += 1;
      activeId = id;
    },
    activeId: () => activeId,
    writes: () => writes,
  };
}

describe('history session model', () => {
  it('reads and writes the existing session store', () => {
    expect(browserSessionStore.load).toBe(loadSessions);
    expect(browserSessionStore.loadActiveId).toBe(loadActiveSessionId);
    expect(browserSessionStore.saveActiveId).toBe(saveActiveSessionId);
  });

  it('points continue at the existing chat route', () => {
    expect(CONVERSATION_HASH).toBe('#/work/chat');
    expect(CONVERSATION_HASH).toBe(buildAppRouteHash({ ...getDefaultRoute(), view: 'chat' }));
  });

  it('lists newest first with title, preview, count, and active mark', () => {
    const older = session({
      id: 'old',
      title: '夜班交接',
      updatedAt: now - 3 * 3_600_000,
      messages: [
        { id: 'm1', role: 'user', content: '把夜班交接寫成三點。', timestamp: now - 3 * 3_600_000 },
      ],
    });
    const newer = session({
      id: 'new',
      title: '   ',
      updatedAt: now - 30_000,
      messages: [
        { id: 'm2', role: 'user', content: '  一號鍋爐\n壓力偏高  ', timestamp: now - 60_000 },
        { id: 'm3', role: 'assistant', content: '   ', timestamp: now - 40_000 },
      ],
    });
    const store = memoryStore([older, newer], 'old');
    const rows = listHistory(store, now);
    expect(rows.map((row) => row.id)).toEqual(['new', 'old']);
    expect(rows[0]).toMatchObject({
      title: '新對話',
      preview: '一號鍋爐 壓力偏高',
      messageCount: 1,
      when: '剛剛',
      active: false,
    });
    expect(rows[1]).toMatchObject({
      title: '夜班交接',
      messageCount: 1,
      when: '3 小時前',
      active: true,
    });
  });

  it('formats older timestamps with the zh-TW calendar date', () => {
    const ts = now - 26 * 3_600_000;
    expect(formatHistoryWhen(ts, now)).toBe(new Date(ts).toLocaleDateString('zh-TW'));
    expect(formatHistoryWhen(now - 5 * 60_000, now)).toBe('5 分鐘前');
  });

  it('collapses preview whitespace and caps length', () => {
    const content = `起 ${'壓'.repeat(90)} 終`;
    expect(previewText([{ id: 'm', role: 'user', content, timestamp: now }])).toBe(
      `${content.replace(/\s+/g, ' ').slice(0, 80)}…`,
    );
    expect(previewText([])).toBe('沒有內容');
    expect(sessionTitle('  ')).toBe('新對話');
  });

  it('opens one record and hides blank turns', () => {
    const store = memoryStore([
      session({
        id: 'a',
        title: '鍋爐壓力偏高',
        messages: [
          { id: 'u', role: 'user', content: '先看哪幾個點？', timestamp: now - 120_000 },
          { id: 'blank', role: 'assistant', content: '  ', timestamp: now - 90_000 },
          { id: 'b', role: 'assistant', content: '先看汽包壓力。', timestamp: now - 60_000 },
        ],
      }),
    ]);
    const opened = openHistory(store, 'a', now);
    expect(opened?.turns.map((turn) => turn.content)).toEqual(['先看哪幾個點？', '先看汽包壓力。']);
    expect(opened?.turns.map((turn) => turn.label)).toEqual(['你', '回應']);
    expect(opened?.messageCount).toBe(2);
    expect(openHistory(store, 'missing', now)).toBeNull();
  });

  it('resumes an existing session without replacing the stored list', () => {
    const sessions = [session({ id: 'a', title: '甲' }), session({ id: 'b', title: '乙' })];
    const store = memoryStore(sessions, 'b');
    expect(resumeHistory(store, 'missing')).toBeNull();
    expect(store.writes()).toBe(0);
    expect(store.activeId()).toBe('b');

    expect(resumeHistory(store, 'a')).toEqual({ id: 'a', hash: '#/work/chat' });
    expect(store.writes()).toBe(1);
    expect(store.activeId()).toBe('a');
    expect(store.load()).toBe(sessions);
    expect(listHistory(store, now).find((row) => row.id === 'a')?.active).toBe(true);
  });
});
