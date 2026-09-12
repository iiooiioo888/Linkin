/**
 * ChatView — 對話主表面。
 * 底部詳細區（文件／終端／問題／Context）一律常駐；僅有進行中／互動中任務時才左右分裂右側監控。
 * Context（dsh-context 風格）主表面固定在底部詳細區，不跳監看台。
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { ChatMessage, TaskProgress } from '../types';
import { cancelTask, fetchTask, resumeTask } from '../api/client';
import { useBodyScrollLock } from '../hooks/useBodyScrollLock';
import { useIsMobileLiteShell } from '../hooks/useMediaQuery';
import InputBar from './InputBar';
import type { SendOptions } from './InputBar';
import MessageList from './MessageList';
import ErrorState from './ui/ErrorState';
import RahoDecisionBar from './RahoDecisionBar';
import ChatBottomPanel from './ChatBottomPanel';
import type { BottomTab } from './ChatBottomPanel';
import ChatTaskMonitor from './ChatTaskMonitor';
import {
  activeTaskMessage,
  flattenWsNodes,
  hasUnresolvedDecision,
  isBattleWaiting,
  isGrillInteractive,
  numBudget,
  resolveContextTaskId,
  runningTaskMessage,
  wsFiles,
  wsProblems,
  wsTerminal,
} from '../lib/chatWorkspace';
import PipelineStrip from './chat/PipelineStrip';
import {
  OPEN_CHAT_CONTEXT_EVENT,
  consumePendingChatContext,
  openContextModal,
} from '../lib/contextUi';
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
  onOpenBilling?: () => void;
  /** SSE 本輪實際扣款（優先於任務預算 liveSpent） */
  liveSpent?: number | null;
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
  onOpenBilling,
  liveSpent: sseLiveSpent,
}: ChatViewProps) {
  const live = activeTaskMessage(messages);
  const runningMsg = runningTaskMessage(messages);
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

  const task = live?.taskState ?? runningMsg?.taskState ?? hydrated;
  const pending = task?.raho?.pending_decisions ?? [];
  const running = task?.status === 'running' || task?.status === 'pending';
  const grilling = messages.some((m) => Boolean(m.grill && !m.grill.locked && !m.grill.terminated));
  const waitingBattle = messages.some(
    (m) => m.battle?.status === 'ESCALATE_TO_USER' && m.battle.waiting_for_user_decision,
  );
  const [monitorPinned, setMonitorPinned] = useState(false);
  const taskFailed = task?.status === 'failed' || task?.status === 'interrupted';
  const needsFullMonitor = Boolean(
    live &&
      (taskFailed ||
        monitorPinned ||
        isGrillInteractive(live) ||
        isBattleWaiting(live) ||
        hasUnresolvedDecision(live)),
  );
  const showPipelineStrip = Boolean(running && !needsFullMonitor);
  const showMonitor = needsFullMonitor;
  const isMobile = useIsMobileLiteShell();
  const [monitorSheetOpen, setMonitorSheetOpen] = useState(false);

  useEffect(() => {
    if (task?.status === 'completed') setMonitorPinned(false);
  }, [task?.status]);

  useEffect(() => {
    if (!showMonitor) setMonitorSheetOpen(false);
  }, [showMonitor]);

  useBodyScrollLock(isMobile && monitorSheetOpen);

  /** 對話詳細區預設 Context（dsh-context）；其餘分頁可切 */
  const [bottomTab, setBottomTab] = useState<BottomTab>('context');
  /** 無進行中任務時預設收合詳細區本體，保留分頁列；/context 會展開 */
  const [bottomOff, setBottomOff] = useState(() => !live);
  const [fileId, setFileId] = useState<string | null>(null);
  const [actError, setActError] = useState<string | null>(null);

  /**
   * 對話頁 Context **永遠**綁定本會話軌跡，禁止跨對話選擇器。
   * - 預設：進行中任務 → 否則本會話最近一則
   * - 點訊息／任務卡 Context：僅當該 taskId 屬於本會話才對準，否則忽略
   */
  const [contextFocusId, setContextFocusId] = useState<string | null>(null);
  const contextTaskId = useMemo(
    () => resolveContextTaskId(messages, contextFocusId),
    [messages, contextFocusId],
  );

  /** 打開底部詳細區 Context；prefer 僅接受本會話 taskId */
  const openContextDetail = (preferTaskId?: string | null) => {
    const explicit = (preferTaskId || '').trim();
    if (explicit) {
      const bound = resolveContextTaskId(messages, explicit);
      // 外來／其他對話 ID：拒絕對準，仍顯示本會話預設軌跡
      setContextFocusId(bound === explicit ? explicit : null);
    } else {
      // /context、導航列：回到本會話預設（live → 最近），不保留舊 focus
      setContextFocusId(null);
    }
    setBottomTab('context');
    setBottomOff(false);
  };

  const openContextDetailRef = useRef(openContextDetail);
  openContextDetailRef.current = openContextDetail;

  // 切換對話會話時回到 Context 分頁，清空跨會話 focus
  useEffect(() => {
    setBottomTab('context');
    setFileId(null);
    setContextFocusId(null);
    setBottomOff(!live);
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps -- 僅在切換會話時重置

  // focus 若已不在本會話 messages 內，自動清掉（防殘留）
  useEffect(() => {
    if (!contextFocusId) return;
    if (resolveContextTaskId(messages, contextFocusId) !== contextFocusId) {
      setContextFocusId(null);
    }
  }, [messages, contextFocusId]);

  // 本會話出現可綁定軌跡時自動展開詳細區（直接顯示對應對話 Context）
  const sawContextRef = useRef(false);
  useEffect(() => {
    if (contextTaskId && !sawContextRef.current) {
      sawContextRef.current = true;
      setBottomTab('context');
      setBottomOff(false);
    }
    if (!contextTaskId) sawContextRef.current = false;
  }, [contextTaskId]);

  useEffect(() => {
    const pending = consumePendingChatContext();
    if (pending !== undefined) {
      // pending 可能來自控制台；仍須經本會話校驗
      openContextDetailRef.current(pending);
    }

    const onOpen = (ev: Event) => {
      const detail = (ev as CustomEvent<{ taskId?: string | null }>).detail;
      const prefer =
        detail && Object.prototype.hasOwnProperty.call(detail, 'taskId')
          ? detail.taskId
          : undefined;
      // 實際綁定一律經本會話 resolve；外來 ID 被忽略
      openContextDetailRef.current(prefer);
    };
    window.addEventListener(OPEN_CHAT_CONTEXT_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_CHAT_CONTEXT_EVENT, onOpen);
  }, []);

  const now = useNowTick(Boolean((showMonitor || showPipelineStrip) && running));
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
      onOpenContext={(tid) => openContextDetail(tid)}
      onSuggest={onSuggest}
      sending={sending}
      onGrillAnswer={onGrillAnswer}
      onBattlePick={onBattlePick}
      hideTaskCard={showMonitor}
    />
  );

  const taskSpent = task ? numBudget(task, 'task_spent') || numBudget(task, 'task_api_spent') : null;
  const liveSpent = sseLiveSpent != null && sseLiveSpent > 0 ? sseLiveSpent : taskSpent;

  const composer = (
    <InputBar
      disabled={sending || grilling || waitingBattle}
      onSend={onSend}
      onOpenBilling={onOpenBilling}
      liveSpent={liveSpent}
      onContextCommand={(mode) => {
        // 對話頁 Context／Peek 一律綁定本會話解析結果，禁止選其他對話
        if (mode === 'peek') {
          openContextModal(contextTaskId);
        } else {
          openContextDetail();
        }
      }}
    />
  );

  return (
    <div
      className={`ws${!showMonitor ? ' is-chat-only' : ' has-monitor'}${monitorSheetOpen ? ' is-monitor-open' : ''}`}
    >
      <div className="ws-main">
        <nav className="ws-nav">
          <div className="ws-crumb">
            對話 / <strong>{title || (showMonitor ? '進行中任務' : '會話')}</strong>
          </div>
          <div className="ws-nav-acts">
            {showMonitor && isMobile && (
              <button
                type="button"
                className="ws-btn ws-btn-primary md:hidden touch-manipulation"
                onClick={() => setMonitorSheetOpen((v) => !v)}
                data-testid="chat-monitor-sheet-toggle"
                aria-expanded={monitorSheetOpen}
              >
                監控
              </button>
            )}
            <button
              type="button"
              className="ws-btn"
              onClick={() => openContextDetail()}
              data-testid="chat-nav-context"
              title="開啟本對話詳細區 Context（/context）· 直接顯示本會話軌跡，不可切換其他對話"
            >
              Context
            </button>
            {onOpenSettings && (
              <button type="button" className="ws-btn ws-btn-icon" onClick={onOpenSettings} aria-label="設定">
                ⚙
              </button>
            )}
          </div>
        </nav>
        {banners}
        {showPipelineStrip && task && (
          <PipelineStrip
            task={task}
            pinned={monitorPinned}
            onPinMonitor={() => setMonitorPinned((v) => !v)}
          />
        )}
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
          taskId={contextTaskId}
          sessionKey={sessionId}
          onProblem={() => {
            setBottomTab('problems');
            setBottomOff(false);
          }}
        />
        {composer}
      </div>
      {isMobile && monitorSheetOpen && showMonitor && (
        <button
          type="button"
          className="ws-monitor-backdrop md:hidden"
          aria-label="關閉任務監控"
          onClick={() => setMonitorSheetOpen(false)}
        />
      )}
      {showMonitor && live && task && (
        <ChatTaskMonitor
          task={task}
          pending={pending}
          running={running}
          now={now}
          onOpenTask={() => onOpenTask(live.id)}
          onOpenTrace={onOpenTrace}
          onOpenContext={() => openContextDetail(task.task_id)}
          onPause={() => void handlePause()}
          onResume={() => void handleResume()}
        />
      )}
      {showMonitor && live && !task && (
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
