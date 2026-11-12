/**
 * 導覽路徑／標題／活動解析 helpers。
 */
import type { MonitorTab } from '../../components/AppShell';
import { getWorldModule, listWorldModules, moduleIdForTab } from '../worldModules';
import { activityTitle, normalizeDeskActivity } from './activity';
import { navItemsForActivity, navPathForTab } from './navGroups';
import { MONITOR_TABS, monitorTabLabel, normalizeMonitorTab } from './tabs';
import type { ActivityKey, ConsoleNavKey, DeskActivityKey } from './types';

export function resolveActivity(
  view: 'chat' | 'monitor' | 'traces' | 'task' | 'raho' | 'company',
  monitorTab: MonitorTab,
): DeskActivityKey {
  if (view === 'chat' || view === 'company' || view === 'traces' || view === 'task' || view === 'raho') {
    return 'work';
  }
  if (moduleIdForTab(monitorTab)) return 'world';
  if (monitorTab === 'live' || monitorTab === 'agents' || monitorTab === 'feedback') return 'observe';
  if (monitorTab === 'models' || monitorTab === 'exec') return 'compute';
  if (monitorTab === 'quota' || monitorTab === 'health') return 'supply';
  if (monitorTab === 'memory' || monitorTab === 'context') return 'assets';
  if (
    monitorTab === 'llm' ||
    monitorTab === 'skills' ||
    monitorTab === 'integrations' ||
    monitorTab === 'ops' ||
    monitorTab === 'lab' ||
    monitorTab === 'metrics' ||
    monitorTab === 'approvals'
  ) {
    // approvals is under work in IA; if somehow on monitor with approvals tab keep work
    if (monitorTab === 'approvals') return 'work';
    return 'settings';
  }
  if (monitorTab === 'tasks') return 'work';
  return 'observe';
}

/** @deprecated 舊「控制台活動」判斷；現改為觀測頂層 */
export function isWorkActivity(
  view: 'chat' | 'monitor' | 'traces' | 'task' | 'raho' | 'company',
  monitorTab: MonitorTab,
): boolean {
  return resolveActivity(view, monitorTab) === 'observe';
}

export function activityNavPath(tab: ConsoleNavKey): string {
  if (tab === 'traces' || tab === 'chat' || tab === 'company') {
    return `${activityTitle('work')} → ${navPathForTab(tab)}`;
  }
  const activity = resolveActivity('monitor', tab as MonitorTab);
  const item =
    navItemsForActivity(activity).find((i) => i.key === tab) ??
    MONITOR_TABS.find((i) => i.key === tab);
  return `${activityTitle(activity)} → ${item?.label ?? String(tab)}`;
}

export function consoleChromeLabel(
  view: 'chat' | 'monitor' | 'traces' | 'task' | 'raho' | 'company',
  monitorTab: MonitorTab,
  _labLabel?: string,
  traceTaskId?: string | null,
): string {
  if (view === 'chat') return '';
  if (view === 'company') return '席位／公司';
  if (view === 'traces') {
    const path = navPathForTab('traces');
    return traceTaskId ? `${path} · ${traceTaskId.slice(0, 8)}…` : path;
  }
  if (view === 'task' || view === 'raho') {
    return `詳情 · ${traceTaskId ? traceTaskId.slice(0, 8) + '…' : ''}`.trimEnd();
  }
  if (monitorTab === 'lab') return _labLabel ? `實驗室 · ${_labLabel}` : '實驗室';
  if (moduleIdForTab(monitorTab)) {
    return monitorTabLabel(monitorTab);
  }
  return navPathForTab(monitorTab);
}

export function defaultTabForActivity(activity: ActivityKey): MonitorTab {
  const resolved = normalizeDeskActivity(activity);
  if (resolved === 'work') return 'tasks';
  if (resolved === 'observe') return 'live';
  if (resolved === 'compute') return 'models';
  if (resolved === 'supply') return 'health';
  if (resolved === 'assets') return 'memory';
  if (resolved === 'settings') return 'llm';
  if (resolved === 'world') {
    const modules = listWorldModules();
    const spec = modules[0];
    if (spec?.defaultPage) return normalizeMonitorTab(spec.defaultPage);
    return 'monitor';
  }
  if (resolved === 'lab') return 'lab';
  const spec = getWorldModule(String(activity));
  if (spec?.defaultPage) return normalizeMonitorTab(spec.defaultPage);
  return 'live';
}
