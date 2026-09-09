/**
 * AppShell — IDE 风格布局容器。
 *
 * 布局：TopBar → [ActivityBar | SidePanel | MainContent | RightPanel] → StatusBar
 * 活動：對話 / 控制台（EvoLoop）/ 靈境（世界）/ Minecraft（建築 + 橋接）/ 實驗室
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { ChatSession } from '../types';
import type { LabSubTab } from '../lib/labTabs';
import {
  ACTIVITY_DEFAULT_TAB,
  isConsoleTab,
  isLinkinTab,
  isMinecraftTab,
  resolveActivity,
  type ActivityKey,
} from '../lib/monitorTabs';
import ActivityBar from './ActivityBar';
import RightPanel from './RightPanel';
import SidePanel from './SidePanel';
import StatusBar from './StatusBar';
import TopBar from './TopBar';

export type ViewKey = 'chat' | 'monitor' | 'traces' | 'task';
/** 精簡後的監控主分頁（次要功能收入 ops / lab）。 */
export type MonitorTab =
  | 'live'
  | 'tasks'
  | 'agents'
  | 'pipeline'
  | 'metrics'
  | 'models'
  | 'feedback'
  | 'lab'
  | 'llm'
  | 'ops'
  | 'memory'
  | 'world'
  | 'npcs'
  | 'quests'
  | 'building'
  | 'items'
  | 'studio'
  | 'minecraft'
  | 'grill';

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
}: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // 切主視圖時展開側欄（功能清單／名冊）
  useEffect(() => {
    setSidebarOpen(true);
  }, [activeView]);

  const activity = resolveActivity(activeView, monitorTab);
  const lastTabByActivity = useRef<Partial<Record<ActivityKey, MonitorTab>>>({});

  useEffect(() => {
    if (activeView === 'traces') {
      lastTabByActivity.current.console = lastTabByActivity.current.console ?? 'live';
      return;
    }
    lastTabByActivity.current[activity] = monitorTab;
  }, [activity, activeView, monitorTab]);

  const handleActivityChange = useCallback(
    (next: ActivityKey) => {
      setSidebarOpen(true);
      if (next === activity) return;
      if (next === 'chat') {
        onViewChange('chat');
        return;
      }
      if (next === 'lab') {
        onMonitorTabChange('lab');
        return;
      }
      if (next === 'linkin') {
        const remembered = lastTabByActivity.current.linkin;
        onMonitorTabChange(
          isLinkinTab(remembered) ? remembered! : (ACTIVITY_DEFAULT_TAB.linkin as MonitorTab),
        );
        return;
      }
      if (next === 'minecraft') {
        const remembered = lastTabByActivity.current.minecraft;
        onMonitorTabChange(
          isMinecraftTab(remembered) ? remembered! : (ACTIVITY_DEFAULT_TAB.minecraft as MonitorTab),
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
      onMonitorTabChange(ACTIVITY_DEFAULT_TAB.console as MonitorTab);
    },
    [activity, activeView, monitorTab, onMonitorTabChange, onViewChange],
  );

  return (
    <div className="flex h-dvh flex-col apple-canvas text-[#F5F5F7]">
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
      <div className="flex min-h-0 flex-1">
        {/* 活动栏 */}
        <ActivityBar activity={activity} onActivityChange={handleActivityChange} />

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
        <main className="flex min-w-0 flex-1 flex-col">{children}</main>

        {/* 右侧 OPC 面板（滑动式） */}
        <RightPanel
          task={rightPanelTask}
          onClose={onRightPanelClose}
        />
      </div>

      {/* ══ 底部状态栏 ══ */}
      <StatusBar
        llmConfigured={llmConfigured}
        taskCount={statusInfo.taskCount}
        memoryCount={statusInfo.memoryCount}
      />
    </div>
  );
}