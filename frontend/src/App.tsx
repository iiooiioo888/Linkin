/**
 * EvoLoop 主应用 — IDE 风格单页布局。
 *
 * 使用 AppShell 作为根布局，整合会话管理、聊天视图、
 * 控制面版视图、OPC 右侧诊断面板。
 *
 * 第二輪重構：狀態與邏輯已拆至 src/hooks（useAppRoute／useChatSessions／
 * useChatSend／useTaskProgressStream／useWorkspaceNavigation），此處只做組裝與 JSX。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { TaskProgress } from './types';
import { fetchConfig, fetchMemories } from './api/client';
import { hydrateWorldModules } from './lib/worldModules';
import AppShell from './components/AppShell';
import ContextModal from './components/ContextModal';
import ChatView from './components/ChatView';
import MonitorView from './components/MonitorView';
import SettingsModal from './components/SettingsModal';
import TraceView from './components/TraceView';
import TaskDetailView from './components/taskdetail/TaskDetailView';
import RahoOpsView from './components/rahoops/RahoOpsView';
import CompanyView from './components/company/CompanyView';
import OnboardingGuide from './components/onboarding/OnboardingGuide';
import { useAppRoute } from './hooks/useAppRoute';
import { useChatSessions } from './hooks/useChatSessions';
import { useChatSend } from './hooks/useChatSend';
import { useWorkspaceNavigation } from './hooks/useWorkspaceNavigation';

export default function App() {
  // ── 外殼狀態（跨 hook 共用） ──
  const [error, setError] = useState<string | null>(null);
  const [rightPanelTask, setRightPanelTask] = useState<TaskProgress | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // ── LLM 配置 ──
  const [llmConfigured, setLlmConfigured] = useState<boolean | null>(null);

  const refreshConfigStatus = useCallback(() => {
    fetchConfig()
      .then((cfg) => setLlmConfigured(cfg.configured))
      .catch(() => setLlmConfigured(null));
  }, []);

  useEffect(() => {
    refreshConfigStatus();
  }, [refreshConfigStatus]);

  useEffect(() => {
    void hydrateWorldModules();
  }, []);

  // ── 記憶計數（狀態列） ──
  const [memoryCount, setMemoryCount] = useState(0);

  useEffect(() => {
    fetchMemories(1, 0)
      .then((data) => setMemoryCount(data.total ?? 0))
      .catch(() => setMemoryCount(0));
    const timer = setInterval(() => {
      fetchMemories(1, 0)
        .then((data) => setMemoryCount(data.total ?? 0))
        .catch(() => {});
    }, 30000);
    return () => clearInterval(timer);
  }, []);

  // ── 路由／會話／發送／導覽 hooks ──
  const route = useAppRoute();
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
  const {
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
  } = useChatSessions({ setError, setRightPanelTask });
  const { sending, lastQuery, sendQuery, handleRetry, handleSuggest } = useChatSend({
    activeSession,
    updateSession,
    setError,
    setRightPanelTask,
  });
  const {
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
  } = useWorkspaceNavigation({ route, activeSession, setRightPanelTask });

  // ── 状态栏信息 ──
  const statusInfo = useMemo(
    () => ({
      taskCount: sessions.reduce((sum, s) => sum + s.messages.filter((m) => m.taskId).length, 0),
      memoryCount,
    }),
    [sessions, memoryCount],
  );

  return (
    <>
      <AppShell
        activeView={activeView}
        onViewChange={handleViewChange}
        rightPanelTask={rightPanelTask}
        onRightPanelClose={() => setRightPanelTask(null)}
        sessions={sessions}
        activeSessionId={activeSession?.id ?? ''}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        onDeleteSession={handleDeleteSession}
        llmConfigured={llmConfigured}
        onOpenSettings={() => setSettingsOpen(true)}
        monitorTab={monitorTab}
        onMonitorTabChange={handleMonitorTabChange}
        focusAgentId={focusAgentId}
        onFocusAgent={handleFocusAgent}
        focusTaskId={focusTaskId}
        onFocusTask={handleFocusTask}
        traceTaskId={traceTaskId}
        onTraceTaskChange={handleTraceTaskChange}
        labSubTab={labSubTab}
        onLabSubTabChange={handleLabSubTabChange}
        statusInfo={statusInfo}
        forceCloseSidebar={decisionPending}
      >
        {activeView === 'chat' && (
          <>
            <OnboardingGuide />
            <ChatView
              messages={activeSession?.messages ?? []}
              sessionId={activeSession?.id ?? ''}
              loading={false}
              sending={sending}
              error={error}
              lastQuery={lastQuery}
              llmConfigured={llmConfigured}
              onOpenSettings={() => setSettingsOpen(true)}
              onSend={sendQuery}
              onRetry={handleRetry}
              onDismissError={() => setError(null)}
              onOpenTask={handleOpenTask}
              onOpenTrace={handleOpenTrace}
              onSuggest={handleSuggest}
              onDecisionPending={handleDecisionPending}
              onDecisionResolved={handleDecisionResolved}
              onTaskStatePatch={handleTaskStatePatch}
            />
          </>
        )}

        {activeView === 'monitor' && (
          <MonitorView
            onOpenTask={handleDashboardOpenTask}
            onOpenTrace={handleOpenTrace}
            messages={activeSession?.messages ?? []}
            activeTab={monitorTab}
            onTabChange={handleMonitorTabChange}
            focusAgentId={focusAgentId}
            onFocusAgent={handleFocusAgent}
            focusTaskId={focusTaskId}
            onFocusTask={handleFocusTask}
            labSubTab={labSubTab}
            onLabSubTabChange={handleLabSubTabChange}
          />
        )}
        {activeView === 'traces' && (
          <TraceView
            taskId={traceTaskId}
            onTaskIdChange={handleTraceTaskChange}
          />
        )}

        {activeView === 'task' && (
          <TaskDetailView
            task={taskDetail}
            loading={taskDetailLoading}
            error={taskDetailError}
            onRefresh={() => {
              if (focusTaskId) void loadTaskDetail(focusTaskId);
            }}
            onBack={() => {
              const origin = taskReturnRef.current;
              taskReturnRef.current = null;
              restoreSurface(origin, 'task', { view: 'monitor', monitorTab: 'tasks', focusTaskId: null });
            }}
            onOpenTrace={handleOpenTrace}
            onOpenRaho={handleOpenRaho}
            onCancel={handleTaskCancel}
            onResume={handleTaskResume}
          />
        )}

        {activeView === 'raho' && (
          <RahoOpsView
            focus={rahoFocus}
            onFocusChange={(focus) => navigateRoute({ view: 'raho', rahoFocus: focus })}
            onOpenTask={openTaskById}
            onBack={() => {
              const origin = rahoReturnRef.current;
              rahoReturnRef.current = null;
              restoreSurface(origin, 'raho', { view: 'monitor', monitorTab: 'agents', focusAgentId: null });
            }}
          />
        )}

        {activeView === 'company' && (
          <CompanyView
            onOpenRole={(roleId) => handleFocusAgent(roleId)}
            onLaunch={(brief, template) => {
              void sendQuery(brief, { executionStrategy: 'company', companyTemplate: template });
              navigateRoute({
                view: 'chat',
                focusAgentId: null,
                focusTaskId: null,
                traceTaskId: null,
                rahoFocus: null,
              });
            }}
            onOpenTask={openTaskById}
            onOpenRaho={() => handleOpenRaho('')}
          />
        )}
      </AppShell>

      {/* LLM 设置弹窗 */}
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={refreshConfigStatus}
        onGoConsole={() => {
          setSettingsOpen(false);
          handleMonitorTabChange('llm');
        }}
        onGoAgents={() => {
          setSettingsOpen(false);
          handleMonitorTabChange('agents');
        }}
        onGoUsage={() => {
          setSettingsOpen(false);
          handleMonitorTabChange('models');
        }}
      />
      <ContextModal
        open={contextModal.open}
        taskId={contextModal.taskId}
        onClose={() => setContextModal((s) => ({ ...s, open: false }))}
      />
    </>
  );
}
