/**
 * SidePanel 監控導覽 sidebar（含角色／任務／API／軌跡名冊切換）。
 */
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { LabSubTab } from '../../lib/labTabs';
import {
  activityTitle,
  navGroupsForActivity,
  resolveActivity,
  type ConsoleNavKey,
} from '../../lib/monitorTabs';
import { partitionNavGroupsForMobileLite } from '../../lib/mobileShell';
import { rosterKindForTab } from '../../lib/worldModules';
import { useIsMobileLiteShell } from '../../hooks/useMediaQuery';
import type { MonitorTab, ViewKey } from '../AppShell';
import TraceRoster from '../TraceRoster';
import { sidePanelMonitorPick } from '../sidePanelNavPick';
import PlaneBadge, { planeKindForActivity } from '../ui/PlaneBadge';
import { AgentRoster } from './AgentRoster';
import { ApiRouteRoster } from './ApiRouteRoster';
import { LabSidebar } from './LabSidebar';
import { TabBtn } from './shared';
import { TaskRoster } from './TaskRoster';

export function MonitorSidebar({
  activeView,
  monitorTab,
  onClose,
  focusAgentId,
  onFocusAgent,
  focusTaskId,
  onFocusTask,
  onMonitorTabChange,
  labSubTab,
  onLabSubTabChange,
  traceTaskId,
  onTraceTaskChange,
  onViewChange,
}: {
  activeView: ViewKey;
  monitorTab: MonitorTab;
  onClose: () => void;
  focusAgentId: string | null;
  onFocusAgent: (id: string | null) => void;
  focusTaskId: string | null;
  onFocusTask: (id: string | null) => void;
  onMonitorTabChange: (tab: MonitorTab, worldModuleId?: string | null) => void;
  labSubTab: LabSubTab;
  onLabSubTabChange: (tab: LabSubTab) => void;
  traceTaskId: string | null;
  onTraceTaskChange: (id: string | null) => void;
  onViewChange?: (view: ViewKey) => void;
}) {
  const { t } = useTranslation();
  const isMobileLite = useIsMobileLiteShell();
  const activity = resolveActivity(activeView, monitorTab);
  const onLab = activity === 'settings' && monitorTab === 'lab';
  const allNavGroups = navGroupsForActivity(activity);
  const { primary: primaryNavGroups, advanced: advancedNavGroups } = useMemo(
    () =>
      isMobileLite
        ? partitionNavGroupsForMobileLite(allNavGroups, activity)
        : { primary: allNavGroups, advanced: [] },
    [allNavGroups, isMobileLite, activity],
  );
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const isWorldNav = activity === 'world';
  const [mcNavOpen, setMcNavOpen] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    for (const group of allNavGroups) {
      init[group.id] = true;
    }
    return init;
  });
  const onAgentsTab = activeView === 'monitor' && monitorTab === 'agents';
  const onStudioTab = activeView === 'monitor' && rosterKindForTab(monitorTab) === 'agents';
  const onMemoryTab = activeView === 'monitor' && monitorTab === 'memory';
  const onRoleDesk = onAgentsTab || onStudioTab || onMemoryTab;
  const onTasksTab = activeView === 'monitor' && monitorTab === 'tasks';
  const onLlmTab = activeView === 'monitor' && monitorTab === 'llm';
  const onTraces = activeView === 'traces';
  const currentKey: ConsoleNavKey =
    activeView === 'chat'
      ? 'chat'
      : activeView === 'company'
        ? 'company'
        : onTraces
          ? 'traces'
          : monitorTab;

  useEffect(() => {
    if (!isWorldNav) return;
    for (const group of allNavGroups) {
      if (group.items.some((item) => item.key === currentKey)) {
        setMcNavOpen((prev) => (prev[group.id] ? prev : { ...prev, [group.id]: true }));
      }
    }
  }, [allNavGroups, currentKey, isWorldNav]);

  const pick = (key: ConsoleNavKey, clickedWorldModuleId?: string) => {
    if (key === 'chat') {
      onViewChange?.('chat');
      onClose();
      return;
    }
    if (key === 'company') {
      onViewChange?.('company');
      onClose();
      return;
    }
    if (key === 'traces') {
      onTraceTaskChange(traceTaskId);
      return;
    }
    const { tab, worldModuleId } = sidePanelMonitorPick(key, clickedWorldModuleId);
    onMonitorTabChange(tab, worldModuleId);
    const keepAgent = key === 'agents' || key === 'memory' || rosterKindForTab(key) === 'agents';
    if (!keepAgent && focusAgentId) onFocusAgent(null);
    if (key !== 'tasks' && focusTaskId) onFocusTask(null);
    if (!keepAgent && key !== 'tasks' && key !== 'llm') onClose();
  };

  if (onLab) {
    return <LabSidebar labSubTab={labSubTab} onLabSubTabChange={onLabSubTabChange} />;
  }

  const showRoster = onRoleDesk || onTasksTab || onTraces || onLlmTab;

  const renderNavGroup = (group: (typeof allNavGroups)[number]) => {
    const groupLabel = group.id === 'mobile-advanced' ? t('mobileShell.advancedNav') : group.label;
    const list = (
      <div className="sp-list">
        {group.items.map((item) => (
          <TabBtn
            key={item.worldModuleId ? `${item.worldModuleId}:${item.key}` : item.key}
            item={item}
            active={currentKey === item.key}
            onClick={() => pick(item.key, item.worldModuleId)}
          />
        ))}
      </div>
    );

    if (isWorldNav && group.id !== 'mobile-advanced') {
      const open = mcNavOpen[group.id] ?? false;
      return (
        <details
          key={group.id}
          className="sp-nav-fold"
          open={open}
          onToggle={(e) => {
            const el = e.currentTarget;
            setMcNavOpen((prev) => ({ ...prev, [group.id]: el.open }));
          }}
        >
          <summary className="sp-group sp-nav-fold__summary">{groupLabel}</summary>
          {list}
        </details>
      );
    }

    const plane = group.plane ?? planeKindForActivity(activity);
    return (
      <div key={group.id}>
        <div className="sp-group flex items-center gap-1.5">
          <span>{groupLabel}</span>
          {plane ? <PlaneBadge kind={plane} /> : null}
        </div>
        {list}
      </div>
    );
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <nav
        className={showRoster ? 'sp-nav sp-nav--roster' : 'sp-nav'}
        aria-label={activityTitle(activity)}
      >
        {primaryNavGroups.map(renderNavGroup)}
        {isMobileLite && advancedNavGroups.length > 0 ? (
          <div>
            <button
              type="button"
              className="sp-group w-full text-left hover:text-[var(--console-ink)]"
              onClick={() => setAdvancedOpen((v) => !v)}
              aria-expanded={advancedOpen}
            >
              {t('mobileShell.advancedNav')} {advancedOpen ? '▾' : '▸'}
            </button>
            {advancedOpen ? advancedNavGroups.map(renderNavGroup) : null}
          </div>
        ) : null}
      </nav>

      {onRoleDesk ? (
        <AgentRoster
          deskScope={onStudioTab ? 'studio' : 'console'}
          focusAgentId={focusAgentId}
          onPick={(id) => {
            onFocusAgent(id);
            onMonitorTabChange(onStudioTab ? 'studio' : 'agents');
          }}
        />
      ) : onTasksTab ? (
        <TaskRoster
          focusTaskId={focusTaskId}
          onPick={(id) => {
            onFocusTask(id);
            onMonitorTabChange('tasks');
          }}
        />
      ) : onLlmTab ? (
        <ApiRouteRoster />
      ) : onTraces ? (
        <TraceRoster
          selectedTaskId={traceTaskId}
          onPick={(id) => {
            onTraceTaskChange(id);
            onClose();
          }}
        />
      ) : null}
    </div>
  );
}
