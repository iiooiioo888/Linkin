/**
 * ChatView — 對話主表面。
 * 底部詳細區（文件／終端／問題／Context）一律常駐；僅有進行中／互動中任務時才左右分裂右側監控。
 * Context（dsh-context 風格）主表面固定在底部詳細區，不跳監看台。
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { TaskProgress } from '../../types';
import { fetchTask, resumeTask } from '../../api/client';
import { useBodyScrollLock } from '../../hooks/useBodyScrollLock';
import { useIsMobileLiteShell } from '../../hooks/useMediaQuery';
import InputBar from '../InputBar';
import MessageList from '../MessageList';
import RahoDecisionBar from '../RahoDecisionBar';
import ChatBottomPanel from '../ChatBottomPanel';
import type { BottomTab } from '../ChatBottomPanel';
import {
  activeTaskMessage,
  flattenWsNodes,
  hasUnresolvedDecision,
  isBattleWaiting,
  isGrillInteractive,
  isRunningTaskStatus,
  isTerminalTaskStatus,
  resolveContextTaskId,
  runningTaskMessage,
  wsFiles,
  wsProblems,
  wsTerminal,
} from '../../lib/chatWorkspace';
import { cancelTaskAndSync } from '../../lib/taskCancel';
import PipelineStrip from '../chat/PipelineStrip';
import {
  OPEN_CHAT_CONTEXT_EVENT,
  consumePendingChatContext,
  openContextModal,
} from '../../lib/contextUi';
import { useNowTick } from '../../lib/taskTiming';
import { ChatConfirmPanel } from './ChatConfirmPanel';
import { ChatMonitorSide } from './ChatMonitorSide';
import { ChatNav } from './ChatNav';
import { ChatNotices } from './ChatNotices';
import type { ChatViewProps } from './types';

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
  onDecisionPending,
  onDecisionResolved,
  onTaskStatePatch,
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

  const task = useMemo(() => {
    const fromMsg = live?.taskState ?? runningMsg?.taskState;
    if (fromMsg && hydrated && fromMsg.task_id === hydrated.task_id) {
      if (isRunningTaskStatus(fromMsg.status) && isTerminalTaskStatus(hydrated.status)) {
        return hydrated;
      }
    }
    return fromMsg ?? hydrated;
  }, [live?.taskState, runningMsg?.taskState, hydrated]);
  const pending = task?.raho?.pending_decisions ?? [];
  const running = task?.status === 'running' || task?.status === 'pending';
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
    if (
      task?.status === 'completed' ||
      task?.status === 'cancelled' ||
      task?.status === 'interrupted'
    ) {
      setMonitorPinned(false);
    }
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
    const { task: fresh, error: cancelErr } = await cancelTaskAndSync(task.task_id);
    if (fresh) {
      onTaskStatePatch?.(task.task_id, fresh);
      setMonitorPinned(false);
      return;
    }
    if (cancelErr) {
      setActError(cancelErr);
      return;
    }
    onTaskStatePatch?.(task.task_id, { status: 'cancelled' });
    setMonitorPinned(false);
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
      <ChatNotices
        llmConfigured={llmConfigured}
        onOpenSettings={onOpenSettings}
        error={error}
        lastQuery={lastQuery}
        onRetry={onRetry}
        onDismissError={onDismissError}
        actError={actError}
        setActError={setActError}
      />
      <ChatConfirmPanel
        messages={messages}
        setActError={setActError}
        onTaskStatePatch={onTaskStatePatch}
      />
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
      onTaskStatePatch={onTaskStatePatch}
      hideTaskCard={showMonitor}
    />
  );

  const composer = (
    <InputBar
      disabled={sending}
      onSend={onSend}
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
      className={`ws flex min-h-0 flex-1 flex-col${!showMonitor ? ' is-chat-only' : ' has-monitor'}${monitorSheetOpen ? ' is-monitor-open' : ''}`}
    >
      <div className="ws-main">
        <ChatNav
          title={title}
          showMonitor={showMonitor}
          isMobile={isMobile}
          monitorSheetOpen={monitorSheetOpen}
          setMonitorSheetOpen={setMonitorSheetOpen}
          openContextDetail={openContextDetail}
          onOpenSettings={onOpenSettings}
        />
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
      <ChatMonitorSide
        isMobile={isMobile}
        monitorSheetOpen={monitorSheetOpen}
        setMonitorSheetOpen={setMonitorSheetOpen}
        showMonitor={showMonitor}
        live={live}
        task={task}
        pending={pending}
        running={running}
        now={now}
        onOpenTask={onOpenTask}
        onOpenTrace={onOpenTrace}
        openContextDetail={openContextDetail}
        handlePause={handlePause}
        handleResume={handleResume}
      />
    </div>
  );
}
