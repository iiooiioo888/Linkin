/**
 * 監控中心分頁定義（單一資料源）。
 *
 * 左側：
 *   ActivityBar（對話 / 控制台 / 已註冊世界模組 / 實驗室）
 *   → SidePanel 分組功能
 *   → 上下文清單（會話／名冊／軌跡）
 *
 * 對話／控制台／實驗室 = EvoLoop（總覽／執行／審計／計費／系統）
 * 世界模組（目前 Minecraft）= 世界觀／Admin／內容／建築／橋接；不進控制台
 */
import type { MonitorTab } from '../components/AppShell';
import {
  getWorldModule,
  hashPageForTab,
  isModuleActivity,
  listWorldModules,
  moduleIdForTab,
  normalizeActivityAlias,
  resolveModulePage,
  type ModuleNavGroup,
  type ModuleNavItem,
} from './worldModules';

export type CoreActivityKey = 'chat' | 'console' | 'lab';
export type ActivityKey = CoreActivityKey | string;

export type ConsoleNavKey = MonitorTab | 'traces';

export type MonitorTabItem = { key: MonitorTab; icon: string; label: string };
export type ConsoleNavItem = { key: ConsoleNavKey; icon: string; label: string; hint?: string };

export type MonitorNavGroupId = 'overview' | 'execute' | 'roles' | 'observe' | 'system' | string;

export type MonitorNavGroup = {
  id: MonitorNavGroupId;
  label: string;
  items: ConsoleNavItem[];
};

export const TRACES_NAV_ITEM: ConsoleNavItem = {
  key: 'traces',
  icon: '☰',
  label: '軌跡',
  hint: '執行步驟',
};

export const MONITOR_WORK_TABS: MonitorTabItem[] = [
  { key: 'live', icon: '◎', label: '即時' },
  { key: 'tasks', icon: '▣', label: '任務' },
  { key: 'agents', icon: '◈', label: '角色' },
  { key: 'pipeline', icon: '⬡', label: '管線' },
];

export const MONITOR_AUDIT_TABS: MonitorTabItem[] = [
  { key: 'feedback', icon: '♥', label: '用戶反饋' },
  { key: 'metrics', icon: '◇', label: '系統總覽' },
];

export const MONITOR_BILLING_TABS: MonitorTabItem[] = [
  { key: 'credits', icon: '◎', label: '靈境積分' },
  { key: 'models', icon: '◉', label: 'AI 用量' },
];

export const MONITOR_SETUP_TABS: MonitorTabItem[] = [
  { key: 'llm', icon: '⊞', label: 'API 路由' },
];

export const MONITOR_SYSTEM_TABS: MonitorTabItem[] = [
  { key: 'memory', icon: '◌', label: 'L0 核心' },
  { key: 'context', icon: '◫', label: 'Context' },
  { key: 'integrations', icon: '⧉', label: '外部整合' },
  { key: 'skills', icon: '⚡', label: '技能與 MCP' },
  { key: 'ops', icon: '⚙', label: '基礎設施' },
];

export const CONSOLE_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'overview',
    label: '總覽',
    items: [{ key: 'live', icon: '◎', label: '即時', hint: '總覽，點卡片跳轉' }],
  },
  {
    id: 'execute',
    label: '執行',
    items: [
      { key: 'tasks', icon: '▣', label: '任務', hint: '隊列／執行中／已完成' },
      { key: 'pipeline', icon: '⬡', label: '管線', hint: '反思閉環階段' },
      TRACES_NAV_ITEM,
    ],
  },
  {
    id: 'roles',
    label: '角色',
    items: [{ key: 'agents', icon: '◈', label: '角色', hint: '質詢鏈與角色工作台合一' }],
  },
  {
    id: 'audit',
    label: '審計',
    items: [
      { key: 'feedback', icon: '♥', label: '用戶反饋', hint: '評分與審計留痕' },
      { key: 'metrics', icon: '◇', label: '系統總覽', hint: '快取／反思／優化' },
    ],
  },
  {
    id: 'billing',
    label: '計費',
    items: [
      { key: 'credits', icon: '◎', label: '靈境積分', hint: '積分、Docker/阿里雲帳單、貢獻與管理' },
      { key: 'models', icon: '◉', label: 'AI 用量', hint: 'Token 延遲與模型成本' },
    ],
  },
  {
    id: 'system',
    label: '系統',
    items: [
      { key: 'llm', icon: '⊞', label: 'API 路由', hint: '金鑰、目錄、分發' },
      { key: 'memory', icon: '◌', label: 'L0 核心', hint: '記憶／知識／態勢雷達' },
      { key: 'context', icon: '◫', label: 'Context', hint: '控制台鏡像；主表面在對話詳細區' },
      { key: 'integrations', icon: '⧉', label: '外部整合', hint: 'MemOS／Viking／WeKnora／Yao／Ouroboros／OpenPencil' },
      { key: 'skills', icon: '⚡', label: '技能與 MCP', hint: '技能庫／MCP／dsh-context 可視化' },
      { key: 'ops', icon: '⚙', label: '基礎設施', hint: 'Hub／檢查點／連線池' },
    ],
  },
];

function moduleNavAsGroups(id: string): MonitorNavGroup[] {
  const spec = getWorldModule(id);
  if (!spec) return [];
  return spec.navGroups.map((group: ModuleNavGroup) => ({
    id: group.id,
    label: group.label,
    items: group.items.map((item: ModuleNavItem) => ({
      key: item.key as ConsoleNavKey,
      icon: item.icon,
      label: item.label,
      hint: item.hint,
    })),
  }));
}

function allNavGroups(): MonitorNavGroup[] {
  return [
    ...CONSOLE_NAV_GROUPS,
    ...listWorldModules().flatMap((spec) => moduleNavAsGroups(spec.id)),
  ];
}

export const MONITOR_NAV_GROUPS: MonitorNavGroup[] = CONSOLE_NAV_GROUPS;

export const LAB_TAB: MonitorTabItem = { key: 'lab', icon: '✦', label: '實驗室' };

export const MONITOR_TABS: MonitorTabItem[] = [
  ...MONITOR_SETUP_TABS,
  ...MONITOR_WORK_TABS,
  ...MONITOR_AUDIT_TABS,
  ...MONITOR_BILLING_TABS,
  ...MONITOR_SYSTEM_TABS,
  LAB_TAB,
];

export const MONITOR_PRIMARY_TABS = MONITOR_WORK_TABS;

export const MONITOR_MORE_TABS: MonitorTabItem[] = [
  ...MONITOR_AUDIT_TABS,
  ...MONITOR_BILLING_TABS,
  ...MONITOR_SYSTEM_TABS,
  LAB_TAB,
];

/** 僅控制台別名。世界模組頁別名在 worldModules.MODULE_PAGE_ALIASES。 */
export const CONSOLE_TAB_ALIASES: Record<string, MonitorTab> = {
  overview: 'live',
  balancer: 'live',
  task: 'tasks',
  dashboard: 'tasks',
  hub: 'ops',
  cloud: 'credits',
  docker: 'credits',
  billing: 'credits',
  credits: 'credits',
  wallet: 'credits',
  usage: 'models',
  observe: 'models',
  checkpoints: 'ops',
  opc: 'metrics',
  dbpool: 'ops',
  routes: 'llm',
  l0: 'memory',
  context: 'context',
  ctx: 'context',
  dshcontext: 'context',
  integrate: 'integrations',
  integration: 'integrations',
  memos: 'integrations',
  openviking: 'integrations',
  weknora: 'integrations',
  yao: 'integrations',
  ouroboros: 'integrations',
  openpencil: 'integrations',
  grill: 'agents',
};
export const MONITOR_TAB_ALIASES = CONSOLE_TAB_ALIASES;

const WORK_TAB_KEYS = new Set<string>(MONITOR_WORK_TABS.map((t) => t.key));
const CONSOLE_TAB_KEYS = new Set<string>([
  ...MONITOR_SETUP_TABS.map((t) => t.key),
  ...MONITOR_WORK_TABS.map((t) => t.key),
  ...MONITOR_AUDIT_TABS.map((t) => t.key),
  ...MONITOR_BILLING_TABS.map((t) => t.key),
  ...MONITOR_SYSTEM_TABS.map((t) => t.key),
]);
const CORE_PAGE_KEYS = new Set<string>([...CONSOLE_TAB_KEYS, 'lab']);

export const CONSOLE_CHROME_TABS: Array<{ key: MonitorTab; label: string; match: MonitorTab[] }> = [
  { key: 'live', label: '總覽', match: ['live'] },
  { key: 'tasks', label: '執行', match: ['tasks', 'pipeline'] },
  { key: 'agents', label: '角色', match: ['agents'] },
  { key: 'feedback', label: '審計', match: ['feedback', 'metrics'] },
  { key: 'credits', label: '計費', match: ['credits', 'models', 'billing'] },
  { key: 'llm', label: '系統', match: ['llm', 'ops', 'memory', 'context', 'integrations', 'skills'] },
];

export function consoleChromeTabKey(tab: MonitorTab | 'traces'): MonitorTab | null {
  if (tab === 'traces') return 'tasks';
  return CONSOLE_CHROME_TABS.find((item) => item.match.includes(tab))?.key ?? null;
}

export const ACTIVITY_DEFAULT_TAB: Partial<Record<ActivityKey, MonitorTab | 'traces'>> = {
  console: 'live',
  lab: 'lab',
  minecraft: 'monitor',
};

export function normalizeMonitorTab(tab: string | null | undefined): MonitorTab {
  if (!tab) return 'live';
  if (CORE_PAGE_KEYS.has(tab)) return tab as MonitorTab;
  if (CONSOLE_TAB_ALIASES[tab]) return CONSOLE_TAB_ALIASES[tab];
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

export function resolveActivity(
  view: 'chat' | 'monitor' | 'traces' | 'task' | 'raho',
  monitorTab: MonitorTab,
): ActivityKey {
  if (view === 'chat') return 'chat';
  if (view === 'traces' || view === 'task' || view === 'raho') return 'console';
  if (monitorTab === 'lab') return 'lab';
  const moduleId = moduleIdForTab(monitorTab);
  if (moduleId) return moduleId;
  return 'console';
}

export function isWorkActivity(
  view: 'chat' | 'monitor' | 'traces' | 'task' | 'raho',
  monitorTab: MonitorTab,
): boolean {
  return resolveActivity(view, monitorTab) === 'console';
}

export function navGroupsForActivity(activity: ActivityKey): MonitorNavGroup[] {
  const resolved = normalizeActivityAlias(activity) ?? activity;
  if (resolved === 'console') return CONSOLE_NAV_GROUPS;
  if (isModuleActivity(resolved)) return moduleNavAsGroups(resolved);
  return [];
}

export function navItemsForActivity(activity: ActivityKey): MonitorTabItem[] {
  const resolved = normalizeActivityAlias(activity) ?? activity;
  if (resolved === 'console') {
    return [
      ...MONITOR_SETUP_TABS,
      ...MONITOR_WORK_TABS,
      ...MONITOR_AUDIT_TABS,
      ...MONITOR_BILLING_TABS,
      ...MONITOR_SYSTEM_TABS,
    ];
  }
  if (isModuleActivity(resolved)) {
    return moduleNavAsGroups(resolved).flatMap((group) =>
      group.items
        .filter((item) => item.key !== 'traces')
        .map((item) => ({ key: item.key as MonitorTab, icon: item.icon, label: item.label })),
    );
  }
  return [];
}

export function activityTitle(activity: ActivityKey): string {
  if (activity === 'chat') return '對話';
  if (activity === 'lab') return '實驗室';
  if (activity === 'console') return '控制台';
  const spec = getWorldModule(normalizeActivityAlias(activity) ?? activity);
  return spec?.title ?? '模組';
}

export function navGroupForTab(tab: ConsoleNavKey): MonitorNavGroup['id'] | null {
  return allNavGroups().find((g) => g.items.some((i) => i.key === tab))?.id ?? null;
}

export function navPathForTab(tab: ConsoleNavKey): string {
  const group = allNavGroups().find((g) => g.items.some((i) => i.key === tab));
  const item = group?.items.find((i) => i.key === tab);
  if (!group || !item) return item?.label ?? monitorTabLabel(tab as MonitorTab);
  return `${group.label} → ${item.label}`;
}

export function activityNavPath(tab: ConsoleNavKey): string {
  if (tab === 'traces') return `${activityTitle('console')} → ${navPathForTab('traces')}`;
  const activity = resolveActivity('monitor', tab);
  const item =
    navItemsForActivity(activity).find((i) => i.key === tab) ??
    MONITOR_TABS.find((i) => i.key === tab);
  return `${activityTitle(activity)} → ${item?.label ?? String(tab)}`;
}

export function consoleChromeLabel(
  view: 'chat' | 'monitor' | 'traces' | 'task' | 'raho',
  monitorTab: MonitorTab,
  _labLabel?: string,
  traceTaskId?: string | null,
): string {
  if (view === 'chat') return '';
  if (view === 'traces') {
    const path = navPathForTab('traces');
    return traceTaskId ? `${path} · ${traceTaskId.slice(0, 8)}…` : path;
  }
  if (view === 'task' || view === 'raho') return `詳情 · ${traceTaskId ? traceTaskId.slice(0, 8) + '…' : ''}`.trimEnd();
  if (monitorTab === 'lab') return _labLabel ? `實驗室 · ${_labLabel}` : '實驗室';
  if (moduleIdForTab(monitorTab)) {
    return monitorTabLabel(monitorTab);
  }
  return navPathForTab(monitorTab);
}

export function isWorkTab(tab: MonitorTab): boolean {
  return WORK_TAB_KEYS.has(tab);
}

export function defaultTabForActivity(activity: ActivityKey): MonitorTab {
  const resolved = normalizeActivityAlias(activity) ?? activity;
  if (resolved === 'lab') return 'lab';
  if (resolved === 'console' || resolved === 'chat') return 'live';
  const spec = getWorldModule(resolved);
  if (spec?.defaultPage) return normalizeMonitorTab(spec.defaultPage);
  return 'live';
}

export function isCoreActivity(activity: ActivityKey): activity is CoreActivityKey {
  return activity === 'chat' || activity === 'console' || activity === 'lab';
}

export { hashPageForTab, listWorldModules, moduleIdForTab };
