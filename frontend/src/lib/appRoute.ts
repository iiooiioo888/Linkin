/**
 * Hash 路由 — 支援書籤與刷新還原。
 *
 * 格式：
 *   #/chat
 *   #/monitor | #/monitor/tasks | #/monitor/tasks/{taskId}
 *   #/monitor/agents/{agentId}
 *   #/monitor/lab | #/monitor/lab/{prompt|firecrawl|archify|ponytail|quant|maps|mcp|ab}
 *   #/monitor/world | #/monitor/npcs | #/monitor/quests | #/monitor/items | #/monitor/studio
 *   #/monitor/building | #/monitor/minecraft | #/monitor/admin
 *   #/modules/{id} | #/modules/{id}/{page}   世界模組（Minecraft…）
 *   #/traces | #/traces/{taskId}
 *   #/task/{taskId}                 任務詳情整頁（需求分析與一切分析產物）
 *   #/raho | #/raho/{runId|taskId}  公司運行時席位 I/O 監察整頁
 */
import type { MonitorTab, ViewKey } from '../components/AppShell';
import { markGrillReveal, setPendingDeskTab } from './agentUi';
import { normalizeLabSubTab, type LabSubTab } from './labTabs';
import { normalizeMonitorTab } from './monitorTabs';
import { getWorldModule, hashPageForTab, moduleIdForTab, tabForModulePage } from './worldModules';

export interface AppRoute {
  view: ViewKey;
  monitorTab: MonitorTab;
  focusAgentId: string | null;
  focusTaskId: string | null;
  traceTaskId: string | null;
  /** 監察頁聚焦對象：raho run_id 或 task_id（兩者可互查） */
  rahoFocus: string | null;
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
    rahoFocus: null,
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

  if (head === 'modules') {
    const moduleId = parts[1] ? decodeURIComponent(parts[1]) : '';
    const spec = getWorldModule(moduleId);
    const rawPage = parts[2] ? decodeURIComponent(parts[2]) : spec?.defaultPage ?? 'world';
    const tab = normalizeMonitorTab(tabForModulePage(rawPage) ?? rawPage);
    return {
      view: 'monitor',
      monitorTab: spec ? tab : 'live',
      focusAgentId: (tab === 'agents' || tab === 'studio') && parts[3] ? decodeURIComponent(parts[3]) : null,
      focusTaskId: null,
      traceTaskId: null,
      rahoFocus: null,
      labSubTab: 'prompt',
    };
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
      rahoFocus: null,
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

  // 任務詳情整頁：#/task/{taskId}
  if (head === 'task') {
    return {
      ...getDefaultRoute(),
      view: 'task',
      focusTaskId: parts[1] ? decodeURIComponent(parts[1]) : null,
    };
  }

  // 公司運行時席位 I/O 監察整頁：#/raho | #/raho/{runId|taskId}
  if (head === 'raho') {
    return {
      ...getDefaultRoute(),
      view: 'raho',
      rahoFocus: parts[1] ? decodeURIComponent(parts[1]) : null,
    };
  }

  return getDefaultRoute();
}

export function buildAppRouteHash(route: AppRoute): string {
  if (route.view === 'chat') return '#/chat';

  if (route.view === 'monitor') {
    const moduleId = moduleIdForTab(route.monitorTab);
    if (moduleId) {
      const page = hashPageForTab(route.monitorTab, moduleId);
      if (route.monitorTab === 'studio' && route.focusAgentId) {
        return `#/modules/${encodeURIComponent(moduleId)}/studio/${encodeURIComponent(route.focusAgentId)}`;
      }
      if (page === getWorldModule(moduleId)?.defaultPage) {
        return `#/modules/${encodeURIComponent(moduleId)}`;
      }
      return `#/modules/${encodeURIComponent(moduleId)}/${encodeURIComponent(page)}`;
    }
    if (route.monitorTab === 'agents' && route.focusAgentId) {
      return `#/monitor/agents/${encodeURIComponent(route.focusAgentId)}`;
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

  if (route.view === 'task') {
    return route.focusTaskId
      ? `#/task/${encodeURIComponent(route.focusTaskId)}`
      : '#/chat';
  }

  if (route.view === 'raho') {
    return route.rahoFocus ? `#/raho/${encodeURIComponent(route.rahoFocus)}` : '#/raho';
  }

  return '#/chat';
}

export function appRouteFromState(params: {
  activeView: ViewKey;
  monitorTab: MonitorTab;
  focusAgentId: string | null;
  focusTaskId: string | null;
  traceTaskId: string | null;
  rahoFocus: string | null;
  labSubTab: LabSubTab;
}): AppRoute {
  return {
    view: params.activeView,
    monitorTab: params.monitorTab,
    focusAgentId: params.focusAgentId,
    focusTaskId: params.focusTaskId,
    traceTaskId: params.traceTaskId,
    rahoFocus: params.rahoFocus,
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
    a.rahoFocus === b.rahoFocus &&
    a.labSubTab === b.labSubTab
  );
}

export function applyAppRoute(route: AppRoute): {
  activeView: ViewKey;
  monitorTab: MonitorTab;
  focusAgentId: string | null;
  focusTaskId: string | null;
  traceTaskId: string | null;
  rahoFocus: string | null;
  labSubTab: LabSubTab;
} {
  return {
    activeView: route.view,
    monitorTab: route.monitorTab,
    focusAgentId: route.focusAgentId,
    focusTaskId: route.focusTaskId,
    traceTaskId: route.traceTaskId,
    rahoFocus: route.rahoFocus,
    labSubTab: route.labSubTab,
  };
}
