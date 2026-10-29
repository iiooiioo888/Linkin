/**
 * Agent Desk 導航（Phase1）— 頂層活動＋側欄樹單一資料源。
 *
 * 頂層：工作／觀測／計算／供給／資產／世界／設定
 * 舊活動別名（chat／console／lab／company）仍可解析，對照至少一版。
 */
import type { MonitorTab } from '../components/AppShell';
import {
  getWorldModule,
  hashPageForTab,
  isModuleActivity,
  listWorldModules,
  moduleIdForTab,
  normalizeActivityAlias as normalizeModuleActivityAlias,
  resolveModulePage,
  type ModuleNavGroup,
  type ModuleNavItem,
} from './worldModules';

/** Phase1 頂層活動 */
export type DeskActivityKey =
  | 'work'
  | 'observe'
  | 'compute'
  | 'supply'
  | 'assets'
  | 'world'
  | 'settings';

/** @deprecated 舊 CoreActivityKey；請用 DeskActivityKey。仍接受別名。 */
export type CoreActivityKey = 'chat' | 'console' | 'lab' | 'company' | DeskActivityKey;
export type ActivityKey = DeskActivityKey | CoreActivityKey | string;

/** 側欄可點項目：既有 MonitorTab + 視圖切換鍵 + Phase1 空殼鍵 */
export type ConsoleNavKey = MonitorTab | 'traces' | 'chat' | 'company';

export type MonitorTabItem = { key: MonitorTab; icon: string; label: string };
export type ConsoleNavItem = {
  key: ConsoleNavKey;
  icon: string;
  label: string;
  hint?: string;
};

export type MonitorNavGroupId =
  | 'work'
  | 'observe'
  | 'compute'
  | 'supply'
  | 'assets'
  | 'settings'
  | 'overview'
  | 'execute'
  | 'roles'
  | 'observe-legacy'
  | 'system'
  | string;

export type MonitorNavGroup = {
  id: MonitorNavGroupId;
  label: string;
  /** 平面徽章：compute→AI-Core／supply→Cloud Core／assets→只存與取 */
  plane?: 'ai-core' | 'cloud-core' | 'assets';
  items: ConsoleNavItem[];
};

export const DESK_ACTIVITIES: ReadonlyArray<{
  key: DeskActivityKey;
  label: string;
  icon: string;
}> = [
  { key: 'work', label: '工作', icon: '▣' },
  { key: 'observe', label: '觀測', icon: '◎' },
  { key: 'compute', label: '計算', icon: '◉' },
  { key: 'supply', label: '供給', icon: '☁' },
  { key: 'assets', label: '資產', icon: '◌' },
  { key: 'world', label: '世界', icon: '⬡' },
  { key: 'settings', label: '設定', icon: '⚙' },
];

/** 舊活動 → 新頂層 */
export const ACTIVITY_ALIASES: Record<string, DeskActivityKey> = {
  chat: 'work',
  console: 'observe',
  lab: 'settings',
  company: 'work',
  minecraft: 'world',
};

export function normalizeDeskActivity(activity: ActivityKey): DeskActivityKey | string {
  if (
    activity === 'work' ||
    activity === 'observe' ||
    activity === 'compute' ||
    activity === 'supply' ||
    activity === 'assets' ||
    activity === 'world' ||
    activity === 'settings'
  ) {
    return activity;
  }
  if (ACTIVITY_ALIASES[activity]) return ACTIVITY_ALIASES[activity];
  const moduleAlias = normalizeModuleActivityAlias(activity);
  if (moduleAlias && getWorldModule(moduleAlias)) return 'world';
  if (getWorldModule(activity)) return 'world';
  return activity;
}

export const TRACES_NAV_ITEM: ConsoleNavItem = {
  key: 'traces',
  icon: '☰',
  label: '軌跡',
  hint: '執行步驟',
};

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

/** Phase1 側欄：工作 */
export const WORK_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'work',
    label: '工作',
    items: [
      { key: 'chat', icon: '◎', label: '對話', hint: 'Linkin 決定做什麼' },
      { key: 'tasks', icon: '▣', label: '任務', hint: '隊列／執行中／已完成' },
      TRACES_NAV_ITEM,
      { key: 'company', icon: '⌂', label: '席位／公司', hint: '席位與交辦' },
      { key: 'approvals', icon: '✓', label: '審批佇列', hint: 'A2 前未開通' },
    ],
  },
];

/** Phase1 側欄：觀測 */
export const OBSERVE_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'observe',
    label: '觀測',
    items: [
      { key: 'live', icon: '◎', label: 'Agent 總覽', hint: '首屏指標' },
      { key: 'agents', icon: '◈', label: '角色工作台', hint: '角色工作台' },
      { key: 'feedback', icon: '♥', label: '用戶反饋', hint: '評分與審計留痕' },
    ],
  },
];

/** Phase1 側欄：計算（AI-Core） */
export const COMPUTE_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'compute',
    label: '計算',
    plane: 'ai-core',
    items: [
      { key: 'models', icon: '◉', label: '模型與成本', hint: 'Token 延遲與模型成本 · AI-Core' },
      { key: 'exec', icon: '⬡', label: '執行環境', hint: '沙箱／Exec · 無資料則空態' },
    ],
  },
];

/** Phase1 側欄：供給（Cloud Core） */
export const SUPPLY_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'supply',
    label: '供給',
    plane: 'cloud-core',
    items: [
      { key: 'quota', icon: '▤', label: '容量與配額', hint: 'Cloud Core 配額帳本' },
      { key: 'health', icon: '◇', label: '節點健康', hint: '節點／基礎設施健康' },
    ],
  },
];

/** Phase1 側欄：資產 */
export const ASSETS_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'assets',
    label: '資產',
    plane: 'assets',
    items: [
      { key: 'context', icon: '◫', label: 'Context', hint: '資產層只存與取' },
      { key: 'memory', icon: '◌', label: '記憶瀏覽', hint: '只存與取，不決策' },
    ],
  },
];

/** Phase1 側欄：設定 */
export const SETTINGS_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'settings',
    label: '設定',
    items: [
      { key: 'llm', icon: '⊞', label: 'API 路由', hint: '金鑰、目錄、分發' },
      { key: 'skills', icon: '⚡', label: '技能與 MCP', hint: '技能庫／MCP' },
      { key: 'integrations', icon: '⧉', label: '外部整合', hint: '召回／工作流／設計' },
      { key: 'ops', icon: '⚙', label: '基礎設施', hint: 'Hub／檢查點／連線池' },
      { key: 'lab', icon: '✦', label: '實驗室', hint: '開發工具' },
      { key: 'metrics', icon: '◇', label: '系統總覽', hint: '快取／反思／優化' },
    ],
  },
];

/** 舊單一控制台樹（相容匯出；新碼用分活動組） */
export const CONSOLE_NAV_GROUPS: MonitorNavGroup[] = [
  ...OBSERVE_NAV_GROUPS,
  {
    id: 'execute',
    label: '執行',
    items: [
      { key: 'tasks', icon: '▣', label: '任務', hint: '隊列／執行中／已完成' },
      TRACES_NAV_ITEM,
    ],
  },
  {
    id: 'roles',
    label: '角色',
    items: [{ key: 'agents', icon: '◈', label: '角色', hint: '角色工作台' }],
  },
  ...COMPUTE_NAV_GROUPS,
  ...ASSETS_NAV_GROUPS,
  ...SETTINGS_NAV_GROUPS,
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
    ...WORK_NAV_GROUPS,
    ...OBSERVE_NAV_GROUPS,
    ...COMPUTE_NAV_GROUPS,
    ...SUPPLY_NAV_GROUPS,
    ...ASSETS_NAV_GROUPS,
    ...SETTINGS_NAV_GROUPS,
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

/** 僅觀測別名。世界模組頁別名在 worldModules.MODULE_PAGE_ALIASES。 */
export const CONSOLE_TAB_ALIASES: Record<string, MonitorTab> = {
  overview: 'live',
  balancer: 'live',
  task: 'tasks',
  pipeline: 'agents',
  dashboard: 'tasks',
  hub: 'ops',
  cloud: 'ops',
  docker: 'ops',
  billing: 'models',
  credits: 'models',
  wallet: 'models',
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
  /** Phase1 新路徑段 → MonitorTab */
  approvals: 'approvals',
  exec: 'exec',
  quota: 'quota',
  health: 'health',
  memory: 'memory',
};
export const MONITOR_TAB_ALIASES = CONSOLE_TAB_ALIASES;

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

export const ACTIVITY_DEFAULT_TAB: Partial<Record<ActivityKey, MonitorTab | 'traces' | 'chat' | 'company'>> = {
  work: 'chat',
  observe: 'live',
  compute: 'models',
  supply: 'health',
  assets: 'memory',
  world: 'monitor',
  settings: 'llm',
  /** 舊別名 */
  console: 'live',
  lab: 'lab',
  chat: 'chat',
  company: 'company',
  minecraft: 'monitor',
};

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

export function navGroupsForActivity(activity: ActivityKey): MonitorNavGroup[] {
  const resolved = normalizeDeskActivity(activity);
  if (resolved === 'work') return WORK_NAV_GROUPS;
  if (resolved === 'observe') return OBSERVE_NAV_GROUPS;
  if (resolved === 'compute') return COMPUTE_NAV_GROUPS;
  if (resolved === 'supply') return SUPPLY_NAV_GROUPS;
  if (resolved === 'assets') return ASSETS_NAV_GROUPS;
  if (resolved === 'settings') return SETTINGS_NAV_GROUPS;
  if (resolved === 'world') {
    const modules = listWorldModules();
    if (modules.length === 0) return [];
    return modules.flatMap((spec) => moduleNavAsGroups(spec.id));
  }
  if (isModuleActivity(String(activity))) return moduleNavAsGroups(String(activity));
  return [];
}

export function navItemsForActivity(activity: ActivityKey): MonitorTabItem[] {
  return navGroupsForActivity(activity).flatMap((group) =>
    group.items
      .filter((item) => item.key !== 'traces' && item.key !== 'chat' && item.key !== 'company')
      .map((item) => ({ key: item.key as MonitorTab, icon: item.icon, label: item.label })),
  );
}

export function activityTitle(activity: ActivityKey): string {
  const resolved = normalizeDeskActivity(activity);
  const found = DESK_ACTIVITIES.find((a) => a.key === resolved);
  if (found) return found.label;
  const spec = getWorldModule(normalizeModuleActivityAlias(String(activity)) ?? String(activity));
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

export function isWorkTab(tab: MonitorTab): boolean {
  return WORK_TAB_KEYS.has(tab);
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

/** 桌面 ActivityBar 是否為 Desk 頂層（非世界模組 id） */
export function isCoreActivity(activity: ActivityKey): activity is DeskActivityKey {
  const resolved = normalizeDeskActivity(activity);
  return (
    resolved === 'work' ||
    resolved === 'observe' ||
    resolved === 'compute' ||
    resolved === 'supply' ||
    resolved === 'assets' ||
    resolved === 'world' ||
    resolved === 'settings'
  );
}

export function isDeskActivity(activity: ActivityKey): activity is DeskActivityKey {
  return isCoreActivity(activity);
}

export { hashPageForTab, listWorldModules, moduleIdForTab };
