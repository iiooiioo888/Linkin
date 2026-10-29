/**
 * Hash 路由 — 支援書籤與刷新還原。
 *
 * Phase1 新路徑（寫出優先）＋舊別名雙讀至少一版：
 *   #/work/chat|tasks|traces|company|approvals
 *   #/observe/overview|agents|feedback
 *   #/compute/models|exec
 *   #/supply/quota|health
 *   #/assets/context|memory
 *   #/world/{module}/…
 *   #/settings/routes|skills|integrations|ops|lab/…
 *
 * 舊格式仍可解析：
 *   #/chat #/monitor/* #/traces #/task/{id} #/company #/raho #/modules/…
 */
import type { MonitorTab, ViewKey } from '../components/AppShell';
import { markGrillReveal, setPendingDeskTab } from './agentUi';
import { normalizeLabSubTab, type LabSubTab } from './labTabs';
import { normalizeMonitorTab } from './monitorTabs';
import { getWorldModule, hashPageForTab, moduleIdForTab, tabForModulePage } from './worldModules';

let pendingSkillFocus: string | null = null;

/** `#/monitor/skills/{id}` 或 `#/settings/skills/{id}` 正規化後仍要把該技能捲到畫面裡。 */
export function rememberSkillFocus(id: string) {
  pendingSkillFocus = id;
}

export function takeSkillFocus(): string | null {
  const id = pendingSkillFocus;
  pendingSkillFocus = null;
  return id;
}

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

/** Phase1 平面段 → 內部 MonitorTab／View */
const PLANE_TAB_MAP: Record<string, Record<string, { view?: ViewKey; tab?: MonitorTab }>> = {
  work: {
    chat: { view: 'chat' },
    tasks: { view: 'monitor', tab: 'tasks' },
    traces: { view: 'traces' },
    company: { view: 'company' },
    approvals: { view: 'monitor', tab: 'approvals' },
  },
  observe: {
    overview: { view: 'monitor', tab: 'live' },
    agents: { view: 'monitor', tab: 'agents' },
    feedback: { view: 'monitor', tab: 'feedback' },
  },
  compute: {
    models: { view: 'monitor', tab: 'models' },
    exec: { view: 'monitor', tab: 'exec' },
  },
  supply: {
    quota: { view: 'monitor', tab: 'quota' },
    health: { view: 'monitor', tab: 'health' },
  },
  assets: {
    context: { view: 'monitor', tab: 'context' },
    memory: { view: 'monitor', tab: 'memory' },
  },
  settings: {
    routes: { view: 'monitor', tab: 'llm' },
    skills: { view: 'monitor', tab: 'skills' },
    integrations: { view: 'monitor', tab: 'integrations' },
    ops: { view: 'monitor', tab: 'ops' },
    lab: { view: 'monitor', tab: 'lab' },
    metrics: { view: 'monitor', tab: 'metrics' },
  },
};

function parsePlaneRoute(parts: string[]): AppRoute | null {
  const plane = parts[0];
  const leaf = parts[1] ?? '';
  const map = PLANE_TAB_MAP[plane];
  if (!map) return null;

  if (plane === 'work' && leaf === 'tasks' && parts[2]) {
    return {
      ...getDefaultRoute(),
      view: 'monitor',
      monitorTab: 'tasks',
      focusTaskId: decodeURIComponent(parts[2]),
    };
  }
  if (plane === 'work' && leaf === 'traces') {
    return {
      ...getDefaultRoute(),
      view: 'traces',
      traceTaskId: parts[2] ? decodeURIComponent(parts[2]) : null,
    };
  }
  if (plane === 'work' && leaf === 'company') {
    if (parts[2] === 'raho') {
      return {
        ...getDefaultRoute(),
        view: 'raho',
        rahoFocus: parts[3] ? decodeURIComponent(parts[3]) : null,
      };
    }
    return { ...getDefaultRoute(), view: 'company' };
  }
  if (plane === 'observe' && leaf === 'agents' && parts[2]) {
    return {
      ...getDefaultRoute(),
      view: 'monitor',
      monitorTab: 'agents',
      focusAgentId: decodeURIComponent(parts[2]),
    };
  }
  if (plane === 'assets' && leaf === 'context' && parts[2]) {
    return {
      ...getDefaultRoute(),
      view: 'monitor',
      monitorTab: 'context',
      focusTaskId: decodeURIComponent(parts[2]),
    };
  }
  if (plane === 'settings' && leaf === 'skills' && parts[2]) {
    rememberSkillFocus(decodeURIComponent(parts[2]));
    return { ...getDefaultRoute(), view: 'monitor', monitorTab: 'skills' };
  }
  if (plane === 'settings' && leaf === 'lab') {
    const sub = normalizeLabSubTab(parts[2] ? decodeURIComponent(parts[2]) : null);
    return { ...getDefaultRoute(), view: 'monitor', monitorTab: 'lab', labSubTab: sub };
  }
  if (plane === 'settings' && leaf === 'integrations' && parts[2]) {
    return { ...getDefaultRoute(), view: 'monitor', monitorTab: 'integrations' };
  }

  const entry = map[leaf] ?? (plane === 'observe' && !leaf ? map.overview : undefined);
  if (!entry) {
    // 平面根：落到該平面預設頁
    const defaults: Record<string, { view: ViewKey; tab?: MonitorTab }> = {
      work: { view: 'chat' },
      observe: { view: 'monitor', tab: 'live' },
      compute: { view: 'monitor', tab: 'models' },
      supply: { view: 'monitor', tab: 'health' },
      assets: { view: 'monitor', tab: 'memory' },
      settings: { view: 'monitor', tab: 'llm' },
    };
    const d = defaults[plane];
    if (!d) return null;
    return {
      ...getDefaultRoute(),
      view: d.view,
      monitorTab: d.tab ?? 'live',
    };
  }
  return {
    ...getDefaultRoute(),
    view: entry.view ?? 'monitor',
    monitorTab: entry.tab ?? 'live',
  };
}

function parseWorldRoute(parts: string[]): AppRoute {
  // #/world/{moduleId}/{page?} 或舊 #/modules/…
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

export function parseAppRoute(hash: string): AppRoute {
  const raw = hash.replace(/^#/, '').replace(/^\/?/, '');
  if (!raw) return getDefaultRoute();

  const parts = raw.split('/').filter(Boolean);
  const head = parts[0];

  // Phase1 新平面路徑
  if (
    head === 'work' ||
    head === 'observe' ||
    head === 'compute' ||
    head === 'supply' ||
    head === 'assets' ||
    head === 'settings'
  ) {
    return parsePlaneRoute(parts) ?? getDefaultRoute();
  }

  if (head === 'world') {
    return parseWorldRoute(parts);
  }

  if (head === 'chat') {
    return { ...getDefaultRoute(), view: 'chat' };
  }

  if (head === 'modules') {
    return parseWorldRoute(parts);
  }

  if (head === 'monitor') {
    const rawTab = parts[1] ?? 'live';
    if (rawTab === 'credits' || rawTab === 'billing' || rawTab === 'wallet') {
      return {
        ...getDefaultRoute(),
        view: 'monitor',
        monitorTab: 'models',
      };
    }
    if (rawTab === 'grill') {
      setPendingDeskTab('tasks');
      markGrillReveal();
    }
    const tab = normalizeMonitorTab(rawTab);
    const focusRaw = parts[2] ? decodeURIComponent(parts[2]) : null;
    if (tab === 'skills' && focusRaw) rememberSkillFocus(focusRaw);
    const labSubTab = tab === 'lab' ? normalizeLabSubTab(focusRaw) : 'prompt';
    return {
      view: 'monitor',
      monitorTab: tab,
      focusAgentId: (tab === 'agents' || tab === 'studio') && focusRaw ? focusRaw : null,
      focusTaskId:
        (tab === 'tasks' || tab === 'context') && focusRaw ? focusRaw : null,
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

  if (head === 'task') {
    return {
      ...getDefaultRoute(),
      view: 'task',
      focusTaskId: parts[1] ? decodeURIComponent(parts[1]) : null,
    };
  }

  if (head === 'company') {
    return { ...getDefaultRoute(), view: 'company' };
  }

  if (head === 'raho') {
    return {
      ...getDefaultRoute(),
      view: 'raho',
      rahoFocus: parts[1] ? decodeURIComponent(parts[1]) : null,
    };
  }

  return getDefaultRoute();
}

/** 寫出 Phase1 新路徑（舊別名仍由 parse 雙讀）。 */
export function buildAppRouteHash(route: AppRoute): string {
  if (route.view === 'chat') return '#/work/chat';

  if (route.view === 'traces') {
    return route.traceTaskId
      ? `#/work/traces/${encodeURIComponent(route.traceTaskId)}`
      : '#/work/traces';
  }

  if (route.view === 'task') {
    // 任務詳情整頁維持 #/task/{id} 雙別名；亦支援 #/work/tasks/{id} 列表深鏈
    return route.focusTaskId
      ? `#/task/${encodeURIComponent(route.focusTaskId)}`
      : '#/work/chat';
  }

  if (route.view === 'raho') {
    return route.rahoFocus
      ? `#/work/company/raho/${encodeURIComponent(route.rahoFocus)}`
      : '#/work/company/raho';
  }

  if (route.view === 'company') return '#/work/company';

  if (route.view === 'monitor') {
    const moduleId = moduleIdForTab(route.monitorTab);
    if (moduleId) {
      const page = hashPageForTab(route.monitorTab, moduleId);
      if (route.monitorTab === 'studio' && route.focusAgentId) {
        return `#/world/${encodeURIComponent(moduleId)}/studio/${encodeURIComponent(route.focusAgentId)}`;
      }
      if (page === getWorldModule(moduleId)?.defaultPage) {
        return `#/world/${encodeURIComponent(moduleId)}`;
      }
      return `#/world/${encodeURIComponent(moduleId)}/${encodeURIComponent(page)}`;
    }

    const tab = route.monitorTab;
    if (tab === 'live') return '#/observe/overview';
    if (tab === 'agents') {
      return route.focusAgentId
        ? `#/observe/agents/${encodeURIComponent(route.focusAgentId)}`
        : '#/observe/agents';
    }
    if (tab === 'feedback') return '#/observe/feedback';
    if (tab === 'tasks') {
      return route.focusTaskId
        ? `#/work/tasks/${encodeURIComponent(route.focusTaskId)}`
        : '#/work/tasks';
    }
    if (tab === 'approvals') return '#/work/approvals';
    if (tab === 'models') return '#/compute/models';
    if (tab === 'exec') return '#/compute/exec';
    if (tab === 'quota') return '#/supply/quota';
    if (tab === 'health') return '#/supply/health';
    if (tab === 'context') {
      return route.focusTaskId
        ? `#/assets/context/${encodeURIComponent(route.focusTaskId)}`
        : '#/assets/context';
    }
    if (tab === 'memory') return '#/assets/memory';
    if (tab === 'llm') return '#/settings/routes';
    if (tab === 'skills') return '#/settings/skills';
    if (tab === 'integrations') return '#/settings/integrations';
    if (tab === 'ops') return '#/settings/ops';
    if (tab === 'metrics') return '#/settings/metrics';
    if (tab === 'lab') {
      return route.labSubTab === 'prompt'
        ? '#/settings/lab'
        : `#/settings/lab/${route.labSubTab}`;
    }
    // 未知 tab：保守落到觀測總覽
    return `#/observe/overview`;
  }

  return '#/work/chat';
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
