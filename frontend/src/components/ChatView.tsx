/**
 * ChatView — 無任務只顯示對話；有公司／OPC 任務（含歷史記錄）才左右分裂。
 * 左：主對話 + AI 輸出文件／終端機／問題；右：角色／審計／計費監控。
 */
import { useEffect, useMemo, useState } from 'react';
import type { ChatMessage, TaskProgress } from '../types';
import { cancelTask, fetchTask, resumeTask } from '../api/client';
import InputBar from './InputBar';
import type { SendOptions } from './InputBar';
import MessageList from './MessageList';
import ErrorState from './ui/ErrorState';
import RahoDecisionBar from './RahoDecisionBar';
import ChatBottomPanel from './ChatBottomPanel';
import type { BottomTab } from './ChatBottomPanel';
import ChatTaskMonitor from './ChatTaskMonitor';
import { activeTaskMessage, flattenWsNodes, wsFiles, wsProblems, wsTerminal } from '../lib/chatWorkspace';
import { useNowTick } from '../lib/taskTiming';

interface ChatViewProps {
  messages: ChatMessage[];
  sessionId: string;
  loading: boolean;
  sending: boolean;
  error: string | null;
  lastQuery: string | null;
  llmConfigured?: boolean | null;
  onOpenSettings?: () => void;
  onSend: (text: string, options: SendOptions) => void;
  onRetry: () => void;
  onDismissError: () => void;
  onOpenTask: (messageId: string) => void;
  onOpenTrace?: (taskId: string) => void;
  onSuggest: (text: string, company: boolean) => void;
  onGrillAnswer?: (messageId: string, answer: string, forceLock?: boolean) => void;
  onBattlePick?: (messageId: string, choice: string) => void;
  onDecisionPending?: (hasPending: boolean) => void;
  onDecisionResolved?: (decisionId?: string) => void;
}

export default function ChatView({
  messages,
  sessionId,
  loading,
  sending,
  error,
  lastQuery,
  llmConfigured,
  onOpenSettings,
  onSend,
  onRetry,
  onDismissError,
  onOpenTask,
  onOpenTrace,
  onSuggest,
  onGrillAnswer,
  onBattlePick,
  onDecisionPending,
  onDecisionResolved,
}: ChatViewProps) {
  const live = activeTaskMessage(messages);
  const [hydrated, setHydrated] = useState<TaskProgress | null>(null);
  const taskId = live?.taskId || live?.taskState?.task_id || null;

  useEffect(() => {
    if (!taskId) {
      setHydrated(null);
      return;
    }
    if (live?.taskState) {
      setHydrated(null);
      return;
    }
    let cancelled = false;
    fetchTask(taskId)
      .then((fresh) => {
        if (!cancelled) setHydrated(fresh);
      })
      .catch(() => {
        if (!cancelled) setHydrated(null);
      });
    return () => {
      cancelled = true;
    };
  }, [taskId, live?.taskState]);

  const task = live?.taskState ?? hydrated;
  const pending = task?.raho?.pending_decisions ?? [];
  const grilling = messages.some((m) => Boolean(m.grill && !m.grill.locked && !m.grill.terminated));
  const waitingBattle = messages.some(
    (m) => m.battle?.status === 'ESCALATE_TO_USER' && m.battle.waiting_for_user_decision,
  );
  const showMonitor = Boolean(live);

  const [bottomTab, setBottomTab] = useState<BottomTab>('files');
  const [bottomOff, setBottomOff] = useState(false);
  const [fileId, setFileId] = useState<string | null>(null);
  const [actError, setActError] = useState<string | null>(null);

  const running = task?.status === 'running' || task?.status === 'pending';
  const now = useNowTick(Boolean(showMonitor && running));
  const nodes = useMemo(() => flattenWsNodes(task), [task]);
  const files = useMemo(() => wsFiles(task, nodes), [task, nodes]);
  const terminal = useMemo(() => wsTerminal(task), [task]);
  const problems = useMemo(() => wsProblems(task, pending, nodes), [task, pending, nodes]);
  const title = (task?.query || lastQuery || '').replace(/\s+/g, ' ').slice(0, 48);

  const handlePause = async () => {
    if (!task) return;
    setActError(null);
    try {
      await cancelTask(task.task_id);
    } catch (err) {
      setActError((err as Error).message);
    }
  };

  const handleResume = async () => {
    if (!task) return;
    setActError(null);
    try {
      await resumeTask(task.task_id);
    } catch (err) {
      setActError((err as Error).message);
    }
  };

  const banners = (
    <>
      {llmConfigured === false && (
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[#FF9F0A]/20 bg-[#FF9F0A]/8 px-4 py-2 sm:px-6">
          <p className="text-[12px] text-[#FF9F0A]">尚未配置 API。請先加入千問／DeepSeek／Kimi／OpenRouter。</p>
          {onOpenSettings && (
            <button
              type="button"
              onClick={onOpenSettings}
              className="shrink-0 rounded-lg bg-[#FF9F0A]/15 px-2.5 py-1 text-[11px] font-medium text-[#FF9F0A] hover:bg-[#FF9F0A]/25"
            >
              加入 API
            </button>
          )}
        </div>
      )}
      {error && (
        <div className="shrink-0 px-4 pt-3 sm:px-6">
          <ErrorState
            kind={error.includes('OPC') || error.includes('護欄') ? 'opc_guard' : 'llm'}
            message={error}
            compact
            onRetry={lastQuery ? onRetry : undefined}
            onDismiss={onDismissError}
          />
        </div>
      )}
      {actError && (
        <div className="shrink-0 px-4 pt-3 sm:px-6">
          <ErrorState kind="generic" message={actError} compact onDismiss={() => setActError(null)} />
        </div>
      )}
    </>
  );

  const chat = (
    <MessageList
      messages={messages}
      sessionId={sessionId}
      loading={loading}
      onOpenTask={onOpenTask}
      onOpenTrace={onOpenTrace}
      onSuggest={onSuggest}
      sending={sending}
      onGrillAnswer={onGrillAnswer}
      onBattlePick={onBattlePick}
      hideTaskCard={showMonitor}
    />
  );

  const composer = <InputBar disabled={sending || grilling || waitingBattle} onSend={onSend} />;

  if (!showMonitor) {
    return (
      <div className="flex min-h-0 flex-1">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          {banners}
          {chat}
          {composer}
        </div>
      </div>
    );
  }

  return (
    <div className="ws">
      <div className="ws-main">
        <nav className="ws-nav">
          <div className="ws-crumb">
            對話 / <strong>{title || '進行中任務'}</strong>
          </div>
          <div className="ws-nav-acts">
            {onOpenSettings && (
              <button type="button" className="ws-btn ws-btn-icon" onClick={onOpenSettings} aria-label="設定">
                ⚙
              </button>
            )}
          </div>
        </nav>
        {banners}
        {task && (
          <div className="shrink-0 px-4 pt-2 sm:px-6">
            <RahoDecisionBar
              pending={pending}
              runId={task.raho?.run_id}
              poll
              variant="chat"
              onPendingChange={onDecisionPending}
              onResolved={onDecisionResolved}
            />
          </div>
        )}
        {chat}
        <ChatBottomPanel
          collapsed={bottomOff}
          onToggle={() => setBottomOff((v) => !v)}
          tab={bottomTab}
          onTab={(t) => {
            setBottomTab(t);
            setBottomOff(false);
          }}
          files={files}
          fileId={fileId}
          onFile={setFileId}
          terminal={terminal}
          problems={problems}
          onProblem={() => {
            setBottomTab('problems');
            setBottomOff(false);
          }}
        />
        {composer}
      </div>
      {live && task && (
        <ChatTaskMonitor
          task={task}
          pending={pending}
          running={running}
          now={now}
          onOpenTask={() => onOpenTask(live.id)}
          onOpenTrace={onOpenTrace}
          onPause={() => void handlePause()}
          onResume={() => void handleResume()}
        />
      )}
      {live && !task && (
        <aside className="ws-side" aria-label="任務監控" data-testid="chat-task-monitor">
          <div className="ws-side-h">
            <div>
              <p className="ws-side-k">任務監控</p>
              <p className="ws-side-t">讀取任務快照</p>
            </div>
          </div>
          <div className="ws-side-scroll">
            <p className="ws-empty">正在載入角色／審計／計費…</p>
          </div>
        </aside>
      )}
    </div>
  );
}
