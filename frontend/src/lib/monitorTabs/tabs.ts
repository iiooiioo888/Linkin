/**
 * 監控分頁資料表、別名解析、chrome tabs 與分頁 helpers。
 */
import type { MonitorTab } from '../../components/AppShell';
import { listWorldModules, resolveModulePage } from '../worldModules';
import { CONSOLE_TAB_ALIASES } from './tabAliases';
import type { MonitorTabItem } from './types';

export const MONITOR_WORK_TABS: MonitorTabItem[] = [
  { key: 'live', icon: '◎', label: 'Agent 總覽' },
  { key: 'tasks', icon: '▣', label: '任務' },
  { key: 'agents', icon: '◈', label: '角色' },
];

export const MONITOR_AUDIT_TABS: MonitorTabItem[] = [
  { key: 'feedback', icon: '♥', label: '用戶反饋' },
  { key: 'metrics', icon: '◇', label: '系統總覽' },
];

export const MONITOR_BILLING_TABS: MonitorTabItem[] = [
  { key: 'models', icon: '◉', label: 'AI 用量' },
];

export const MONITOR_SETUP_TABS: MonitorTabItem[] = [
  { key: 'llm', icon: '⊞', label: 'API 路由' },
];

export const MONITOR_SYSTEM_TABS: MonitorTabItem[] = [
  { key: 'memory', icon: '◌', label: '記憶' },
  { key: 'context', icon: '◫', label: 'Context' },
  { key: 'integrations', icon: '⧉', label: '外部整合' },
  { key: 'skills', icon: '⚡', label: '技能與 MCP' },
  { key: 'ops', icon: '⚙', label: '基礎設施' },
];

export const LAB_TAB: MonitorTabItem = { key: 'lab', icon: '✦', label: '實驗室' };

export const MONITOR_TABS: MonitorTabItem[] = [
  ...MONITOR_SETUP_TABS,
  ...MONITOR_WORK_TABS,
  ...MONITOR_AUDIT_TABS,
  ...MONITOR_BILLING_TABS,
  ...MONITOR_SYSTEM_TABS,
  LAB_TAB,
  { key: 'approvals', icon: '✓', label: '審批佇列' },
  { key: 'exec', icon: '⬡', label: '執行環境' },
  { key: 'quota', icon: '▤', label: '容量與配額' },
  { key: 'health', icon: '◇', label: '節點健康' },
];

export const MONITOR_PRIMARY_TABS = MONITOR_WORK_TABS;

export const MONITOR_MORE_TABS: MonitorTabItem[] = [
  ...MONITOR_AUDIT_TABS,
  ...MONITOR_BILLING_TABS,
  ...MONITOR_SYSTEM_TABS,
  LAB_TAB,
];

/** Phase1 空殼頁（後端未開通前誠實空態） */
export const PHASE1_SHELL_TABS = new Set<string>(['approvals', 'exec', 'quota', 'health']);

const WORK_TAB_KEYS = new Set<string>(MONITOR_WORK_TABS.map((t) => t.key));
const CONSOLE_TAB_KEYS = new Set<string>([
  ...MONITOR_SETUP_TABS.map((t) => t.key),
  ...MONITOR_WORK_TABS.map((t) => t.key),
  ...MONITOR_AUDIT_TABS.map((t) => t.key),
  ...MONITOR_BILLING_TABS.map((t) => t.key),
  ...MONITOR_SYSTEM_TABS.map((t) => t.key),
  ...PHASE1_SHELL_TABS,
]);
const CORE_PAGE_KEYS = new Set<string>([...CONSOLE_TAB_KEYS, 'lab']);

export const CONSOLE_CHROME_TABS: Array<{ key: MonitorTab; label: string; match: MonitorTab[] }> = [
  { key: 'live', label: '總覽', match: ['live'] },
  { key: 'tasks', label: '執行', match: ['tasks'] },
  { key: 'agents', label: '角色', match: ['agents'] },
  { key: 'feedback', label: '審計', match: ['feedback', 'metrics'] },
  { key: 'models', label: '計算', match: ['models', 'billing', 'credits', 'exec'] },
  { key: 'llm', label: '設定', match: ['llm', 'ops', 'memory', 'context', 'integrations', 'skills', 'lab'] },
];

export function consoleChromeTabKey(tab: MonitorTab | 'traces'): MonitorTab | null {
  if (tab === 'traces') return 'tasks';
  return CONSOLE_CHROME_TABS.find((item) => item.match.includes(tab))?.key ?? null;
}

export function normalizeMonitorTab(tab: string | null | undefined): MonitorTab {
  if (!tab) return 'live';
  if (CORE_PAGE_KEYS.has(tab)) return tab as MonitorTab;
  if (CONSOLE_TAB_ALIASES[tab] && tab !== 'chat') return CONSOLE_TAB_ALIASES[tab];
  const modulePage = resolveModulePage(tab);
  if (modulePage) return modulePage;
  return 'live';
}

export function monitorTabLabel(tab: MonitorTab): string {
  const consoleItem = MONITOR_TABS.find((item) => item.key === tab);
  if (consoleItem) return consoleItem.label;
  for (const spec of listWorldModules()) {
    for (const group of spec.navGroups) {
      const item = group.items.find((nav) => nav.key === tab);
      if (item) return item.label;
    }
  }
  return tab;
}

export function isMonitorMoreTab(tab: MonitorTab): boolean {
  return MONITOR_MORE_TABS.some((t) => t.key === tab);
}

export function isConsoleTab(tab: MonitorTab | string | null | undefined): boolean {
  return Boolean(tab && CONSOLE_TAB_KEYS.has(tab));
}

export function isPhase1ShellTab(tab: MonitorTab | string | null | undefined): boolean {
  return Boolean(tab && PHASE1_SHELL_TABS.has(tab));
}

export function isWorkTab(tab: MonitorTab): boolean {
  return WORK_TAB_KEYS.has(tab);
}
