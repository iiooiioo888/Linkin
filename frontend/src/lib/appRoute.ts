/**
 * Hash 路由 — 支援書籤與刷新還原。
 *
 * 格式：
 *   #/chat
 *   #/monitor | #/monitor/tasks | #/monitor/tasks/{taskId}
 *   #/monitor/agents/{agentId}
 *   #/monitor/lab | #/monitor/lab/{prompt|firecrawl|archify|ponytail|quant|maps|mcp|ab}
 *   #/monitor/world | #/monitor/npcs | #/monitor/quests | #/monitor/items | #/monitor/studio
 *   #/monitor/building | #/monitor/minecraft
 *   #/traces | #/traces/{taskId}
 */
import type { MonitorTab, ViewKey } from '../components/AppShell';
import { markGrillReveal, setPendingDeskTab } from './agentUi';
import { normalizeLabSubTab, type LabSubTab } from './labTabs';
import { normalizeMonitorTab } from './monitorTabs';

export interface AppRoute {
  view: ViewKey;
  monitorTab: MonitorTab;
  focusAgentId: string | null;
  focusTaskId: string | null;
  traceTaskId: string | null;
  labSubTab: LabSubTab;
}

function defaultView(): ViewKey {
  return import.meta.env.VITE_GITHUB_PAGES === 'true' ? 'monitor' : 'chat';
}

export function getDefaultRoute(): AppRoute {
  return {
    view: defaultView(),
    monitorTab: 'live',
    focusAgentId: null,
    focusTaskId: null,
    traceTaskId: null,
    labSubTab: 'prompt',
  };
}

export function parseAppRoute(hash: string): AppRoute {
  const raw = hash.replace(/^#/, '').replace(/^\/?/, '');
  if (!raw) return getDefaultRoute();

  const parts = raw.split('/').filter(Boolean);
  const head = parts[0];

  if (head === 'chat') {
    return { ...getDefaultRoute(), view: 'chat' };
  }

  if (head === 'monitor') {
    const rawTab = parts[1] ?? 'live';
    if (rawTab === 'grill') {
      setPendingDeskTab('tasks');
      markGrillReveal();
    }
    const tab = normalizeMonitorTab(rawTab);
    const focusRaw = parts[2] ? decodeURIComponent(parts[2]) : null;
    const labSubTab = tab === 'lab' ? normalizeLabSubTab(focusRaw) : 'prompt';
    return {
      view: 'monitor',
      monitorTab: tab,
      focusAgentId: (tab === 'agents' || tab === 'studio') && focusRaw ? focusRaw : null,
      focusTaskId: tab === 'tasks' && focusRaw ? focusRaw : null,
      traceTaskId: null,
      labSubTab,
    };
  }

  if (head === 'traces') {
    const traceTaskId = parts[1] ? decodeURIComponent(parts[1]) : null;
    return {
      ...getDefaultRoute(),
      view: 'traces',
      traceTaskId,
    };
  }

  return getDefaultRoute();
}

export function buildAppRouteHash(route: AppRoute): string {
  if (route.view === 'chat') return '#/chat';

  if (route.view === 'monitor') {
    if (route.monitorTab === 'agents' && route.focusAgentId) {
      return `#/monitor/agents/${encodeURIComponent(route.focusAgentId)}`;
    }
    if (route.monitorTab === 'studio' && route.focusAgentId) {
      return `#/monitor/studio/${encodeURIComponent(route.focusAgentId)}`;
    }
    if (route.monitorTab === 'tasks' && route.focusTaskId) {
      return `#/monitor/tasks/${encodeURIComponent(route.focusTaskId)}`;
    }
    if (route.monitorTab === 'lab') {
      return route.labSubTab === 'prompt' ? '#/monitor/lab' : `#/monitor/lab/${route.labSubTab}`;
    }
    if (route.monitorTab === 'live') return '#/monitor';
    return `#/monitor/${route.monitorTab}`;
  }

  if (route.view === 'traces') {
    return route.traceTaskId
      ? `#/traces/${encodeURIComponent(route.traceTaskId)}`
      : '#/traces';
  }

  return '#/chat';
}

export function appRouteFromState(params: {
  activeView: ViewKey;
  monitorTab: MonitorTab;
  focusAgentId: string | null;
  focusTaskId: string | null;
  traceTaskId: string | null;
  labSubTab: LabSubTab;
}): AppRoute {
  return {
    view: params.activeView,
    monitorTab: params.monitorTab,
    focusAgentId: params.focusAgentId,
    focusTaskId: params.focusTaskId,
    traceTaskId: params.traceTaskId,
    labSubTab: params.labSubTab,
  };
}

/** 寫入 hash；一律用 replaceState，避免 hash 賦值觸發 hashchange 造成更新迴圈。 */
export function syncAppRouteHash(route: AppRoute): void {
  const hash = buildAppRouteHash(route);
  if (window.location.hash === hash) return;
  window.history.replaceState(null, '', hash);
}

export function routesEqual(a: AppRoute, b: AppRoute): boolean {
  return (
    a.view === b.view &&
    a.monitorTab === b.monitorTab &&
    a.focusAgentId === b.focusAgentId &&
    a.focusTaskId === b.focusTaskId &&
    a.traceTaskId === b.traceTaskId &&
    a.labSubTab === b.labSubTab
  );
}

export function applyAppRoute(route: AppRoute): {
  activeView: ViewKey;
  monitorTab: MonitorTab;
  focusAgentId: string | null;
  focusTaskId: string | null;
  traceTaskId: string | null;
  labSubTab: LabSubTab;
} {
  return {
    activeView: route.view,
    monitorTab: route.monitorTab,
    focusAgentId: route.focusAgentId,
    focusTaskId: route.focusTaskId,
    traceTaskId: route.traceTaskId,
    labSubTab: route.labSubTab,
  };
}
