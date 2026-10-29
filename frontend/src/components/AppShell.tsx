/**
 * AppShell — Agent Desk 布局容器。
 *
 * 布局：TopBar → [ActivityBar | SidePanel | MainContent | RightPanel] → 狀態膠囊
 * 活動：工作／觀測／計算／供給／資產／世界／設定（色票 A＝v3 金暗）
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useBodyScrollLock } from '../hooks/useBodyScrollLock';
import { useIsDesktop, useShellMode } from '../hooks/useMediaQuery';
import type { ChatSession } from '../types';
import type { LabSubTab } from '../lib/labTabs';
import {
  defaultTabForActivity,
  isConsoleTab,
  isDeskActivity,
  normalizeDeskActivity,
  resolveActivity,
  type ActivityKey,
} from '../lib/monitorTabs';
import { pagesOfModule } from '../lib/worldModules';
import ActivityBar from './ActivityBar';
import RightPanel from './RightPanel';
import SidePanel from './SidePanel';
import StatusBar from './StatusBar';
import TopBar from './TopBar';

export type ViewKey = 'chat' | 'monitor' | 'traces' | 'task' | 'raho' | 'company';
/** 控制台分頁。模組頁（世界觀／Admin…）是字串鍵，不進此聯合。 */
export type ConsoleTab =
  | 'live'
  | 'tasks'
  | 'agents'
  | 'pipeline'
  | 'metrics'
  | 'models'
  | 'credits'
  | 'billing'
  | 'feedback'
  | 'lab'
  | 'llm'
  | 'ops'
  | 'memory'
  | 'skills'
  | 'integrations'
  | 'context'
  | 'grill';
export type MonitorTab = ConsoleTab | string;

export interface AppShellProps {
  /** 当前活跃视图 */
  activeView: ViewKey;
  onViewChange: (view: ViewKey) => void;

  /** 右侧 OPC 面板内容（TaskProgress） */
  rightPanelTask: import('../types').TaskProgress | null;
  onRightPanelClose: () => void;

  /** 会话列表（SidePanel 用） */
  sessions: ChatSession[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onDeleteSession: (id: string) => void;

  /** LLM 配置状态 */
  llmConfigured: boolean | null;

  /** 打开设置 */
  onOpenSettings: () => void;

  /** 监控中心子分頁 */
  monitorTab: MonitorTab;
  onMonitorTabChange: (tab: MonitorTab) => void;
  focusAgentId: string | null;
  onFocusAgent: (id: string | null) => void;
  focusTaskId: string | null;
  onFocusTask: (id: string | null) => void;

  /** 執行軌跡 */
  traceTaskId: string | null;
  onTraceTaskChange: (id: string | null) => void;

  /** 實驗室子分頁 */
  labSubTab: LabSubTab;
  onLabSubTabChange: (tab: LabSubTab) => void;

  /** 状态栏信息 */
  statusInfo: {
    taskCount: number;
    memoryCount: number;
  };

  /** 主内容区 */
  children: ReactNode;

  /** 有 L5 決策待決時強制收起側欄（避開手機 fixed 遮罩搶點擊） */
  forceCloseSidebar?: boolean;
}

export default function AppShell({
  activeView,
  onViewChange,
  rightPanelTask,
  onRightPanelClose,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  llmConfigured,
  onOpenSettings,
  monitorTab,
  onMonitorTabChange,
  focusAgentId,
  onFocusAgent,
  focusTaskId,
  onFocusTask,
  traceTaskId,
  onTraceTaskChange,
  labSubTab,
  onLabSubTabChange,
  statusInfo,
  children,
  forceCloseSidebar = false,
}: AppShellProps) {
  const isDesktop = useIsDesktop();
  const shellMode = useShellMode();
  const [sidebarOpen, setSidebarOpen] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia('(min-width: 768px)').matches,
  );

  // 切主視圖時：桌面展開側欄；行動端維持關閉以免遮罩蓋住主內容
  useEffect(() => {
    if (activeView === 'company') {
      setSidebarOpen(false);
      return;
    }
    setSidebarOpen(isDesktop);
  }, [activeView, isDesktop]);

  // L5 決策列出現時關閉側欄，否則手機遮罩會蓋住 portal 以外的點擊目標
  useEffect(() => {
    if (forceCloseSidebar) setSidebarOpen(false);
  }, [forceCloseSidebar]);

  const activity = resolveActivity(activeView, monitorTab);
  const lastTabByActivity = useRef<Partial<Record<ActivityKey, MonitorTab>>>({});

  useEffect(() => {
    // 二級整頁（軌跡／任務詳情／席位監察）不參與「上次分頁」記憶，
    // 否則會把它們帶進來的 monitorTab 預設值寫回控制台記憶
    if (activeView === 'company') return;
    if (activeView === 'traces' || activeView === 'task' || activeView === 'raho') {
      lastTabByActivity.current.work = lastTabByActivity.current.work ?? 'tasks';
      return;
    }
    lastTabByActivity.current[activity] = monitorTab;
  }, [activity, activeView, monitorTab]);

  useBodyScrollLock(!isDesktop && sidebarOpen);

  const handleActivityChange = useCallback(
    (next: ActivityKey) => {
      const target = normalizeDeskActivity(next);
      if (isDesktop) setSidebarOpen(true);

      // 舊別名／模組 id 正規化後與當前相同則不跳
      if (target === activity && next !== 'company' && next !== 'chat') return;

      if (target === 'work') {
        // 工作預設進對話；若記憶在任務／審批等則還原 monitor 分頁
        const remembered = lastTabByActivity.current.work;
        if (remembered === 'tasks' || remembered === 'approvals') {
          onMonitorTabChange(remembered);
          return;
        }
        onViewChange('chat');
        return;
      }

      if (target === 'world') {
        const remembered = lastTabByActivity.current.world;
        const pages = pagesOfModule('minecraft');
        onMonitorTabChange(
          remembered && pages.includes(remembered) ? remembered : defaultTabForActivity('world'),
        );
        return;
      }

      if (isDeskActivity(target)) {
        const remembered = lastTabByActivity.current[target];
        if (remembered && (isConsoleTab(remembered) || remembered === 'lab' || remembered === 'exec' || remembered === 'quota' || remembered === 'health' || remembered === 'approvals')) {
          onMonitorTabChange(remembered);
          return;
        }
        onMonitorTabChange(defaultTabForActivity(target));
        return;
      }

      onMonitorTabChange(defaultTabForActivity('observe'));
    },
    [activity, isDesktop, onMonitorTabChange, onViewChange],
  );

  return (
    <div
      className="app-shell flex h-dvh flex-col apple-canvas text-[var(--console-ink)]"
      data-shell-mode={shellMode}
    >
      {/* ══ 顶栏 ══ */}
      <TopBar
        activeView={activeView}
        monitorTab={monitorTab}
        labSubTab={labSubTab}
        traceTaskId={traceTaskId}
        llmConfigured={llmConfigured}
        rightPanelOpen={rightPanelTask !== null}
        onRightPanelToggle={() => {
          if (rightPanelTask) onRightPanelClose();
        }}
        onOpenSettings={onOpenSettings}
        onToggleSidebar={() => setSidebarOpen((v) => !v)}
        onMonitorTabChange={onMonitorTabChange}
        onViewChange={onViewChange}
      />

      {/* ══ 中间区域：ActivityBar + SidePanel + Main + RightPanel ══ */}
      <div className="app-shell__body flex min-h-0 flex-1">
        {/* 桌面左側活動欄 */}
        <ActivityBar
          activity={activity}
          onActivityChange={handleActivityChange}
          placement="sidebar"
        />

        {/* 侧面板（移动端覆盖层） */}
        {activeView !== 'company' && (
        <SidePanel
          activeView={activeView}
          sessions={sessions}
          activeSessionId={activeSessionId}
          open={sidebarOpen}
          onSelectSession={(id) => {
            onSelectSession(id);
            setSidebarOpen(false);
          }}
          onNewSession={onNewSession}
          onDeleteSession={onDeleteSession}
          onClose={() => setSidebarOpen(false)}
          monitorTab={monitorTab}
          onMonitorTabChange={onMonitorTabChange}
          focusAgentId={focusAgentId}
          onFocusAgent={onFocusAgent}
          focusTaskId={focusTaskId}
          onFocusTask={onFocusTask}
          traceTaskId={traceTaskId}
          onTraceTaskChange={onTraceTaskChange}
          labSubTab={labSubTab}
          onLabSubTabChange={onLabSubTabChange}
          onViewChange={onViewChange}
        />
        )}

        {/* 主内容区 */}
        <main className="flex h-full min-h-0 min-w-0 flex-1 flex-col">{children}</main>

        {/* 右侧 OPC 面板（滑动式） */}
        <RightPanel
          task={rightPanelTask}
          onClose={onRightPanelClose}
        />
      </div>

      {/* 行動端底部 Tab 列（桌面僅左側垂直欄） */}
      {!isDesktop && (
        <ActivityBar
          activity={activity}
          activeView={activeView}
          monitorTab={monitorTab}
          onActivityChange={handleActivityChange}
          placement="bottom"
          onMobileTasks={() => {
            onViewChange('monitor');
            onMonitorTabChange('tasks');
          }}
          onMobileUsage={() => {
            onViewChange('monitor');
            onMonitorTabChange('models');
          }}
          onMobileConsoleTab={(tab) => {
            onViewChange('monitor');
            onMonitorTabChange(tab);
          }}

        />
      )}

      {/* ══ 底部状态栏 ══ */}
      <StatusBar
        llmConfigured={llmConfigured}
        taskCount={statusInfo.taskCount}
        memoryCount={statusInfo.memoryCount}
      />
    </div>
  );
}