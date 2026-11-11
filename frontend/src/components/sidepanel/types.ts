/**
 * SidePanel 對外 props 型別。
 */
import type { LabSubTab } from '../../lib/labTabs';
import type { ChatSession } from '../../types';
import type { MonitorTab, ViewKey } from '../AppShell';

export interface SidePanelProps {
  activeView: ViewKey;
  sessions: ChatSession[];
  activeSessionId: string;
  open: boolean;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onDeleteSession: (id: string) => void;
  onClose: () => void;
  monitorTab: MonitorTab;
  onMonitorTabChange: (tab: MonitorTab, worldModuleId?: string | null) => void;
  focusAgentId: string | null;
  onFocusAgent: (id: string | null) => void;
  focusTaskId: string | null;
  onFocusTask: (id: string | null) => void;
  traceTaskId: string | null;
  onTraceTaskChange: (id: string | null) => void;
  labSubTab: LabSubTab;
  onLabSubTabChange: (tab: LabSubTab) => void;
  onViewChange?: (view: ViewKey) => void;
}
