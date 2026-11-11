/**
 * SidePanel — 左側上下文面板。
 * Chat → 會話；Monitor → 完整導航（標題＋說明＋金邊）+ 虛擬滾動名冊。
 */
import { MonitorSidebar } from './MonitorSidebar';
import { SessionList } from './SessionList';
import type { SidePanelProps } from './types';

export default function SidePanel({
  activeView,
  sessions,
  activeSessionId,
  open,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  onClose,
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
  onViewChange,
}: SidePanelProps) {
  return (
    <>
      {open && (
        <div
          className="side-panel-backdrop fixed inset-0 z-20 bg-black/50 md:hidden"
          onClick={onClose}
          aria-hidden
        />
      )}

      <aside
        className={`side-panel-drawer fixed z-30 flex w-[min(280px,88vw)] flex-col overflow-hidden border-r border-white/[0.06] apple-chrome transition-transform md:static md:w-60 md:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between border-b border-white/[0.06] p-2 md:hidden">
          <span className="text-[11px] font-bold text-[var(--console-sub)]">導航</span>
          <button onClick={onClose} className="rounded-lg px-2 py-0.5 text-[var(--console-sub)] hover:bg-white/[0.06]">
            ✕
          </button>
        </div>

        {(activeView === 'monitor' ||
          activeView === 'traces' ||
          activeView === 'chat' ||
          activeView === 'task' ||
          activeView === 'raho') && (
          <MonitorSidebar
            activeView={activeView}
            monitorTab={monitorTab}
            onMonitorTabChange={onMonitorTabChange}
            onClose={onClose}
            focusAgentId={focusAgentId}
            onFocusAgent={onFocusAgent}
            focusTaskId={focusTaskId}
            onFocusTask={onFocusTask}
            labSubTab={labSubTab}
            onLabSubTabChange={onLabSubTabChange}
            traceTaskId={traceTaskId}
            onTraceTaskChange={onTraceTaskChange}
            onViewChange={onViewChange}
          />
        )}
        {activeView === 'chat' && (
          <SessionList
            sessions={sessions}
            activeSessionId={activeSessionId}
            onSelectSession={onSelectSession}
            onNewSession={onNewSession}
            onDeleteSession={onDeleteSession}
          />
        )}
      </aside>
    </>
  );
}
