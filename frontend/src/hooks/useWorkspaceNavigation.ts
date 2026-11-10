/**
 * 工作區導覽：任務詳情整頁、surface 返回、開／關任務、view／monitorTab／
 * labSubTab／focus／trace 切換。
 *
 * 由 App.tsx 抽出，handler 與 effect 的實作、dependency array 均原樣搬移。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Dispatch, RefObject, SetStateAction } from 'react';
import { cancelTask, fetchTask, resumeTask } from '../api/client';
import type { MonitorTab, ViewKey } from '../components/AppShell';
import { isLinkinStudioAgent, requestRoleGrillDesk } from '../lib/agentUi';
import type { AppRoute } from '../lib/appRoute';
import { OPEN_CONTEXT_MODAL_EVENT } from '../lib/contextUi';
import type { OpenContextModalDetail } from '../lib/contextUi';
import type { LabSubTab } from '../lib/labTabs';
import { normalizeMonitorTab } from '../lib/monitorTabs';
import type { ChatSession, TaskProgress } from '../types';
import { usesIndustrialStages } from '../types';
import type { UseAppRouteResult } from './useAppRoute';

export interface UseWorkspaceNavigationOptions {
  route: UseAppRouteResult;
  activeSession: ChatSession | undefined;
  setRightPanelTask: Dispatch<SetStateAction<TaskProgress | null>>;
}

export interface UseWorkspaceNavigationResult {
  taskDetail: TaskProgress | null;
  taskDetailLoading: boolean;
  taskDetailError: string | null;
  /** 浮動 Context Peek 模態（taskId 僅來自呼叫方顯式傳入） */
  contextModal: { open: boolean; taskId: string | null };
  setContextModal: Dispatch<SetStateAction<{ open: boolean; taskId: string | null }>>;
  /** 點進任務／席位頁之前的表面；返回時回到這裡，而不是固定列表。 */
  taskReturnRef: RefObject<AppRoute | null>;
  rahoReturnRef: RefObject<AppRoute | null>;
  restoreSurface: (origin: AppRoute | null, leaving: AppRoute['view'], fallback: Partial<AppRoute>) => void;
  loadTaskDetail: (taskId: string) => Promise<void>;
  openTaskById: (taskId: string) => void;
  handleOpenTask: (messageId: string) => void;
  handleDashboardOpenTask: (task: TaskProgress) => void;
  handleOpenRaho: (focus: string) => void;
  handleOpenTrace: (taskId: string) => void;
  handleViewChange: (view: ViewKey) => void;
  handleMonitorTabChange: (tab: MonitorTab) => void;
  handleLabSubTabChange: (sub: LabSubTab) => void;
  handleFocusAgent: (id: string | null) => void;
  handleFocusTask: (id: string | null) => void;
  handleTraceTaskChange: (id: string | null) => void;
  handleTaskCancel: () => void;
  handleTaskResume: () => void;
}

export function useWorkspaceNavigation({
  route,
  activeSession,
  setRightPanelTask,
}: UseWorkspaceNavigationOptions): UseWorkspaceNavigationResult {
  const {
    activeView,
    monitorTab,
    focusAgentId,
    focusTaskId,
    traceTaskId,
    rahoFocus,
    labSubTab,
    navigateRoute,
  } = route;

  const [contextModal, setContextModal] = useState<{ open: boolean; taskId: string | null }>({
    open: false,
    taskId: null,
  });

  /** 點進任務／席位頁之前的表面；返回時回到這裡，而不是固定列表。 */
  const taskReturnRef = useRef<AppRoute | null>(null);
  const rahoReturnRef = useRef<AppRoute | null>(null);
  const surfaceRef = useRef<AppRoute | null>(null);
  surfaceRef.current = {
    view: activeView,
    monitorTab,
    focusAgentId,
    focusTaskId,
    traceTaskId,
    rahoFocus,
    labSubTab,
  };

  // 浮動 Context 模態（外部事件開啟）
  useEffect(() => {
    const onPeek = (ev: Event) => {
      const detail = (ev as CustomEvent<OpenContextModalDetail>).detail;
      // 僅使用呼叫方顯式傳入的 taskId；禁止用 monitor focusTaskId 頂替（避免跨對話洩漏）
      const explicit =
        detail && Object.prototype.hasOwnProperty.call(detail, 'taskId')
          ? detail.taskId ?? null
          : null;
      setContextModal({ open: true, taskId: explicit });
    };
    window.addEventListener(OPEN_CONTEXT_MODAL_EVENT, onPeek);
    return () => window.removeEventListener(OPEN_CONTEXT_MODAL_EVENT, onPeek);
  }, []);

  // ── 任務詳情整頁（#/task/{taskId}）──
  const [taskDetail, setTaskDetail] = useState<TaskProgress | null>(null);
  const [taskDetailLoading, setTaskDetailLoading] = useState(false);
  const [taskDetailError, setTaskDetailError] = useState<string | null>(null);

  const loadTaskDetail = useCallback(async (taskId: string) => {
    setTaskDetailLoading(true);
    try {
      // events_limit=0：詳情頁要完整事件流，不受列表頁 50 條截斷限制
      const fresh = await fetchTask(taskId, 0);
      setTaskDetail(fresh);
      setTaskDetailError(null);
    } catch (err) {
      setTaskDetailError((err as Error).message || '讀取任務詳情失敗');
    } finally {
      setTaskDetailLoading(false);
    }
  }, []);

  const rememberSurface = useCallback((target: 'task' | 'raho') => {
    const here = surfaceRef.current;
    if (!here || here.view === target) return;
    if (target === 'task') taskReturnRef.current = here;
    else rahoReturnRef.current = here;
  }, []);

  const restoreSurface = useCallback(
    (origin: AppRoute | null, leaving: AppRoute['view'], fallback: Partial<AppRoute>) => {
      if (origin && origin.view !== leaving) {
        navigateRoute(origin);
        return;
      }
      navigateRoute(fallback);
    },
    [navigateRoute],
  );

  const openTaskById = useCallback(
    (taskId: string) => {
      if (!taskId) return;
      rememberSurface('task');
      navigateRoute({ view: 'task', focusTaskId: taskId });
    },
    [navigateRoute, rememberSurface],
  );

  const openTaskDetail = useCallback(
    (task: TaskProgress) => {
      if (!task?.task_id) return;
      setTaskDetail(task);
      setTaskDetailError(null);
      openTaskById(task.task_id);
    },
    [openTaskById],
  );

  // OPC 任務保留右側六級診斷面板；公司／簡單任務進詳情整頁
  const openTaskOrPanel = useCallback(
    (task: TaskProgress) => {
      if (usesIndustrialStages(task)) {
        setRightPanelTask(task);
        return;
      }
      openTaskDetail(task);
    },
    [openTaskDetail],
  );

  const handleOpenRaho = useCallback(
    (focus: string) => {
      rememberSurface('raho');
      navigateRoute({ view: 'raho', rahoFocus: focus || null });
    },
    [navigateRoute, rememberSurface],
  );

  useEffect(() => {
    if (activeView !== 'task' || !focusTaskId) return;
    void loadTaskDetail(focusTaskId);
  }, [activeView, focusTaskId, loadTaskDetail]);

  const handleTaskCancel = useCallback(() => {
    if (!focusTaskId) return;
    void cancelTask(focusTaskId)
      .then(() => loadTaskDetail(focusTaskId))
      .catch((err: Error) => setTaskDetailError(err.message || '請求取消失敗'));
  }, [focusTaskId, loadTaskDetail]);

  const handleTaskResume = useCallback(() => {
    if (!focusTaskId) return;
    void resumeTask(focusTaskId)
      .then(() => loadTaskDetail(focusTaskId))
      .catch((err: Error) => setTaskDetailError(err.message || '斷點續跑失敗'));
  }, [focusTaskId, loadTaskDetail]);

  // ── 从消息打开任务详情 ──
  const handleOpenTask = useCallback(
    (messageId: string) => {
      const msg = activeSession?.messages.find((m) => m.id === messageId);
      if (!msg?.taskState) return;
      openTaskOrPanel(msg.taskState);
    },
    [activeSession, openTaskOrPanel],
  );

  // ── Dashboard 任务打开 ──
  const handleDashboardOpenTask = useCallback((task: TaskProgress) => {
    openTaskOrPanel(task);
  }, [openTaskOrPanel]);

  // ── 打開執行軌跡視圖 ──
  const handleOpenTrace = useCallback(
    (taskId: string) => {
      navigateRoute({ view: 'traces', traceTaskId: taskId });
    },
    [navigateRoute],
  );

  const handleViewChange = useCallback(
    (view: ViewKey) => {
      if (view === 'monitor') {
        // 從其他主視圖切回監控時才清掉 focus；已在監控內則保留書籤路由
        const resetFocus = activeView !== 'monitor';
        navigateRoute({
          view,
          monitorTab,
          focusAgentId: resetFocus ? null : focusAgentId,
          focusTaskId: resetFocus ? null : focusTaskId,
        });
        return;
      }
      if (view === 'traces') {
        navigateRoute({ view, traceTaskId });
        return;
      }
      if (view === 'company') {
        navigateRoute({ view: 'company', focusAgentId: null, focusTaskId: null, traceTaskId: null });
        return;
      }
      navigateRoute({ view: 'chat', focusAgentId: null, focusTaskId: null, traceTaskId: null });
    },
    [navigateRoute, activeView, monitorTab, focusAgentId, focusTaskId, traceTaskId],
  );

  const handleMonitorTabChange = useCallback(
    (tab: MonitorTab) => {
      if (tab === 'grill') {
        requestRoleGrillDesk(focusAgentId && !isLinkinStudioAgent(focusAgentId) ? focusAgentId : undefined);
      }
      const resolved = tab === 'grill' ? 'agents' : normalizeMonitorTab(tab);
      const keepAgent =
        (resolved === 'agents' && !isLinkinStudioAgent(focusAgentId)) ||
        (resolved === 'studio' && isLinkinStudioAgent(focusAgentId));
      navigateRoute({
        view: 'monitor',
        monitorTab: resolved,
        focusAgentId: keepAgent ? focusAgentId : null,
        focusTaskId: resolved === 'tasks' ? focusTaskId : null,
        labSubTab: resolved === 'lab' ? labSubTab : 'prompt',
      });
    },
    [navigateRoute, focusAgentId, focusTaskId, labSubTab],
  );

  const handleLabSubTabChange = useCallback(
    (sub: LabSubTab) => {
      navigateRoute({ view: 'monitor', monitorTab: 'lab', labSubTab: sub });
    },
    [navigateRoute],
  );

  const handleFocusAgent = useCallback(
    (id: string | null) => {
      if (id) {
        navigateRoute({
          view: 'monitor',
          monitorTab: isLinkinStudioAgent(id) ? 'studio' : 'agents',
          focusAgentId: id,
          focusTaskId: null,
        });
        return;
      }
      navigateRoute({
        view: 'monitor',
        monitorTab,
        focusAgentId: null,
      });
    },
    [navigateRoute, monitorTab],
  );

  const handleFocusTask = useCallback(
    (id: string | null) => {
      if (id) {
        navigateRoute({
          view: 'monitor',
          monitorTab: 'tasks',
          focusTaskId: id,
          focusAgentId: null,
        });
        return;
      }
      navigateRoute({
        view: 'monitor',
        monitorTab,
        focusTaskId: null,
      });
    },
    [navigateRoute, monitorTab],
  );

  const handleTraceTaskChange = useCallback(
    (id: string | null) => {
      navigateRoute({ view: 'traces', traceTaskId: id });
    },
    [navigateRoute],
  );

  return {
    taskDetail,
    taskDetailLoading,
    taskDetailError,
    contextModal,
    setContextModal,
    taskReturnRef,
    rahoReturnRef,
    restoreSurface,
    loadTaskDetail,
    openTaskById,
    handleOpenTask,
    handleDashboardOpenTask,
    handleOpenRaho,
    handleOpenTrace,
    handleViewChange,
    handleMonitorTabChange,
    handleLabSubTabChange,
    handleFocusAgent,
    handleFocusTask,
    handleTraceTaskChange,
    handleTaskCancel,
    handleTaskResume,
  };
}
