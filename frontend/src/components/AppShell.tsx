/**
 * AppShell — IDE 风格布局容器。
 *
 * 布局：TopBar → [ActivityBar | SidePanel | MainContent | RightPanel] → StatusBar
 * 活動：對話 / 控制台（EvoLoop）/ 世界模組（Minecraft…）/ 實驗室
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useBodyScrollLock } from '../hooks/useBodyScrollLock';
import { useIsDesktop } from '../hooks/useMediaQuery';
import type { ChatSession } from '../types';
import type { LabSubTab } from '../lib/labTabs';
import {
  defaultTabForActivity,
  isConsoleTab,
  isCoreActivity,
  resolveActivity,
  type ActivityKey,
} from '../lib/monitorTabs';
import { getWorldModule, pagesOfModule } from '../lib/worldModules';
import ActivityBar from './ActivityBar';
import RightPanel from './RightPanel';
import SidePanel from './SidePanel';
import StatusBar from './StatusBar';
import TopBar from './TopBar';

export type ViewKey = 'chat' | 'monitor' | 'traces' | 'task' | 'raho';
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
  const [sidebarOpen, setSidebarOpen] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia('(min-width: 768px)').matches,
  );

  // 切主視圖時：桌面展開側欄；行動端維持關閉以免遮罩蓋住主內容
  useEffect(() => {
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
    if (activeView === 'traces' || activeView === 'task' || activeView === 'raho') {
      lastTabByActivity.current.console = lastTabByActivity.current.console ?? 'live';
      return;
    }
    lastTabByActivity.current[activity] = monitorTab;
  }, [activity, activeView, monitorTab]);

  useBodyScrollLock(!isDesktop && sidebarOpen);

  const handleActivityChange = useCallback(
    (next: ActivityKey) => {
      if (isDesktop) setSidebarOpen(true);
      if (next === activity) return;
      if (next === 'chat') {
        onViewChange('chat');
        return;
      }
      if (next === 'lab') {
        onMonitorTabChange('lab');
        return;
      }
      if (!isCoreActivity(next) && getWorldModule(next)) {
        const remembered = lastTabByActivity.current[next];
        const pages = pagesOfModule(next);
        onMonitorTabChange(
          remembered && pages.includes(remembered) ? remembered : defaultTabForActivity(next),
        );
        return;
      }
      const remembered = lastTabByActivity.current.console;
      if (isConsoleTab(remembered)) {
        onMonitorTabChange(remembered!);
        return;
      }
      if (isConsoleTab(monitorTab) && activeView !== 'chat') {
        onViewChange('monitor');
        return;
      }
      onMonitorTabChange(defaultTabForActivity('console'));
    },
    [activity, activeView, isDesktop, monitorTab, onMonitorTabChange, onViewChange],
  );

  return (
    <div className="app-shell flex h-dvh flex-col apple-canvas text-[var(--console-ink)]">
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
        />

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
          onActivityChange={handleActivityChange}
          placement="bottom"
          onMobileTasks={() => {
            onViewChange('monitor');
            onMonitorTabChange('tasks');
          }}
          onMobileWallet={() => {
            onViewChange('monitor');
            onMonitorTabChange('credits');
          }}
        />
      )}

      {/* ══ 底部状态栏 ══ */}
      <StatusBar
        llmConfigured={llmConfigured}
        taskCount={statusInfo.taskCount}
        memoryCount={statusInfo.memoryCount}
        onOpenCredits={() => {
          onViewChange('monitor');
          onMonitorTabChange('credits');
        }}
      />
    </div>
  );
}