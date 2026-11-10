/**
 * 會話管理：sessions／activeSessionId 狀態、localStorage 載入與持久化、
 * updateSession，新增／切換／刪除會話，以及會話內任務狀態與決策阻塞的更新。
 *
 * 由 App.tsx 抽出，行為與原本的 state／effect／handler 完全一致。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { ChatSession, TaskProgress } from '../types';
import {
  loadActiveSessionId,
  loadSessions,
  newSessionId,
  saveActiveSessionId,
  saveSessions,
} from '../lib/storage';

function createSession(): ChatSession {
  const now = Date.now();
  return {
    id: newSessionId(),
    title: '',
    createdAt: now,
    updatedAt: now,
    messages: [],
  };
}

export interface UseChatSessionsOptions {
  /** 切換會話時清除的對話錯誤 */
  setError: Dispatch<SetStateAction<string | null>>;
  /** 切換會話時收起右側六級診斷面板 */
  setRightPanelTask: Dispatch<SetStateAction<TaskProgress | null>>;
}

export interface UseChatSessionsResult {
  sessions: ChatSession[];
  activeSession: ChatSession | undefined;
  updateSession: (id: string, updater: (s: ChatSession) => ChatSession) => void;
  handleNewSession: () => void;
  handleSelectSession: (id: string) => void;
  handleDeleteSession: (id: string) => void;
  /** 是否仍有待決決策（側欄自動收合用） */
  decisionPending: boolean;
  handleTaskStatePatch: (taskId: string, patch: Partial<TaskProgress> | TaskProgress) => void;
  handleDecisionPending: (hasPending: boolean) => void;
  handleDecisionResolved: (decisionId?: string) => void;
}

export function useChatSessions({
  setError,
  setRightPanelTask,
}: UseChatSessionsOptions): UseChatSessionsResult {
  // ── 会话管理 ──
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    const loaded = loadSessions();
    return loaded.length > 0 ? loaded : [createSession()];
  });
  const [activeId, setActiveId] = useState<string>(() => {
    const saved = loadActiveSessionId();
    const loaded = loadSessions();
    if (saved && loaded.some((s) => s.id === saved)) return saved;
    return loaded[0]?.id ?? '';
  });
  const [decisionPending, setDecisionPending] = useState(false);

  // 初次加载时若无有效 activeId，使用第一个会话
  useEffect(() => {
    if (!activeId && sessions.length > 0) {
      setActiveId(sessions[0].id);
    }
  }, [activeId, sessions]);

  // 持久化
  useEffect(() => {
    saveSessions(sessions);
  }, [sessions]);
  useEffect(() => {
    if (activeId) saveActiveSessionId(activeId);
  }, [activeId]);

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeId) ?? sessions[0],
    [sessions, activeId],
  );

  const updateSession = useCallback(
    (id: string, updater: (s: ChatSession) => ChatSession) => {
      setSessions((prev) => prev.map((s) => (s.id === id ? updater(s) : s)));
    },
    [],
  );

  const handleNewSession = useCallback(() => {
    const session = createSession();
    setSessions((prev) => [session, ...prev]);
    setActiveId(session.id);
    setError(null);
    setRightPanelTask(null);
  }, []);

  const handleSelectSession = useCallback((id: string) => {
    setActiveId(id);
    setError(null);
    setRightPanelTask(null);
  }, []);

  const handleDeleteSession = useCallback(
    (id: string) => {
      setSessions((prev) => {
        const remaining = prev.filter((s) => s.id !== id);
        if (id === activeId) {
          const next = remaining.length > 0 ? remaining[0] : createSession();
          if (remaining.length === 0) remaining.push(next);
          setActiveId(next.id);
        }
        return remaining;
      });
    },
    [activeId],
  );

  const handleTaskStatePatch = useCallback(
    (taskId: string, patch: Partial<TaskProgress> | TaskProgress) => {
      const sid = activeSession?.id;
      if (!sid) return;
      updateSession(sid, (s) => ({
        ...s,
        updatedAt: Date.now(),
        messages: s.messages.map((m) => {
          const tid = (m.taskId || m.taskState?.task_id || '').trim();
          if (tid !== taskId || !m.taskState) return m;
          const nextState = { ...m.taskState, ...patch };
          const terminal =
            nextState.status === 'completed' ||
            nextState.status === 'failed' ||
            nextState.status === 'cancelled' ||
            nextState.status === 'interrupted';
          return {
            ...m,
            streaming: terminal ? false : m.streaming,
            taskState: nextState,
          };
        }),
      }));
    },
    [activeSession?.id, updateSession],
  );

  const handleDecisionPending = useCallback((hasPending: boolean) => {
    setDecisionPending(hasPending);
  }, []);

  const handleDecisionResolved = useCallback(
    (decisionId?: string) => {
      setDecisionPending(false);
      if (!activeSession?.id) return;
      const sid = activeSession.id;
      updateSession(sid, (s) => ({
        ...s,
        messages: s.messages.map((m) => {
          const pending = m.taskState?.raho?.pending_decisions;
          if (!pending?.length) return m;
          const next = decisionId
            ? pending.filter((p) => p.decision_id !== decisionId)
            : [];
          return {
            ...m,
            taskState: {
              ...m.taskState!,
              raho: { ...m.taskState!.raho, pending_decisions: next },
            },
          };
        }),
      }));
    },
    [activeSession?.id, updateSession],
  );

  return {
    sessions,
    activeSession,
    updateSession,
    handleNewSession,
    handleSelectSession,
    handleDeleteSession,
    decisionPending,
    handleTaskStatePatch,
    handleDecisionPending,
    handleDecisionResolved,
  };
}
