/**
 * 監控中心分頁定義（單一資料源）。
 *
 * 左側三層：
 *   ActivityBar（對話 / 控制台 / 靈境 / Minecraft / 實驗室）
 *   → SidePanel 分組功能
 *   → 上下文清單（會話／名冊／軌跡）
 *
 * 對話／控制台／實驗室 = EvoLoop 原功能
 * 靈境                 = 世界內容（憲法／NPC／任務／道具），不連遊戲伺服器
 * Minecraft            = 建築方案與 MineMCP 橋接
 */
import type { MonitorTab } from '../components/AppShell';

export type ActivityKey = 'chat' | 'console' | 'linkin' | 'minecraft' | 'lab';

export type ConsoleNavKey = MonitorTab | 'traces';

export type MonitorTabItem = { key: MonitorTab; icon: string; label: string };
export type ConsoleNavItem = { key: ConsoleNavKey; icon: string; label: string; hint?: string };

export type MonitorNavGroupId =
  | 'setup'
  | 'execute'
  | 'observe'
  | 'system'
  | 'world'
  | 'studio'
  | 'minecraft';

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

export const MONITOR_OBSERVE_TABS: MonitorTabItem[] = [
  { key: 'metrics', icon: '◇', label: '運行指標' },
  { key: 'models', icon: '◉', label: '調用用量' },
  { key: 'feedback', icon: '♥', label: '用戶反饋' },
];

export const MONITOR_SETUP_TABS: MonitorTabItem[] = [
  { key: 'llm', icon: '⊞', label: 'API 路由' },
];

export const MONITOR_SYSTEM_TABS: MonitorTabItem[] = [
  { key: 'memory', icon: '◌', label: 'L0 核心' },
  { key: 'ops', icon: '⚙', label: '基礎設施' },
];

/** 靈境世界內容（非 Minecraft、非控制台公司角色）。 */
export const MONITOR_WORLD_TABS: MonitorTabItem[] = [
  { key: 'world', icon: '✧', label: '世界觀' },
  { key: 'npcs', icon: '☺', label: 'NPC' },
  { key: 'quests', icon: '⚑', label: '任務' },
  { key: 'items', icon: '◆', label: '道具' },
  { key: 'studio', icon: '◈', label: '工作室' },
];

/** Minecraft：建築方案與 MineMCP 橋接（獨立活動，不進靈境側欄）。 */
export const MONITOR_MINECRAFT_TABS: MonitorTabItem[] = [
  { key: 'building', icon: '⌂', label: '建築' },
  { key: 'minecraft', icon: '⇄', label: '橋接' },
];

/** 靈境活動僅世界內容。 */
export const MONITOR_LINKIN_TABS: MonitorTabItem[] = [...MONITOR_WORLD_TABS];

export const CONSOLE_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'setup',
    label: '配置',
    items: [
      { key: 'llm', icon: '⊞', label: 'API 路由', hint: '金鑰、目錄、分發' },
    ],
  },
  {
    id: 'execute',
    label: '執行',
    items: [
      { key: 'live', icon: '◎', label: '即時', hint: '總覽，點卡片跳轉' },
      { key: 'tasks', icon: '▣', label: '任務', hint: '隊列／執行中／已完成' },
      { key: 'agents', icon: '◈', label: '角色', hint: '質詢鏈與角色工作台合一' },
      { key: 'pipeline', icon: '⬡', label: '管線', hint: '反思閉環階段' },
      TRACES_NAV_ITEM,
    ],
  },
  {
    id: 'observe',
    label: '觀測',
    items: [
      { key: 'metrics', icon: '◇', label: '運行指標', hint: '快取／反思／優化' },
      { key: 'models', icon: '◉', label: '調用用量', hint: '延遲與成本' },
      { key: 'feedback', icon: '♥', label: '用戶反饋', hint: '評分紀錄' },
    ],
  },
  {
    id: 'system',
    label: '系統',
    items: [
      { key: 'memory', icon: '◌', label: 'L0 核心', hint: '記憶／知識／態勢雷達' },
      { key: 'ops', icon: '⚙', label: '基礎設施', hint: 'Hub／雲／檢查點／連線池' },
    ],
  },
];

export const LINKIN_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'world',
    label: '世界',
    items: [
      { key: 'world', icon: '✧', label: '世界觀', hint: '憲法與陣營' },
      { key: 'npcs', icon: '☺', label: 'NPC', hint: '角色卡與對話' },
      { key: 'quests', icon: '⚑', label: '任務', hint: '主線／支線／日常' },
      { key: 'items', icon: '◆', label: '道具', hint: '稀有度平衡' },
    ],
  },
  {
    id: 'studio',
    label: '工作室',
    items: [
      { key: 'studio', icon: '◈', label: '工作室角色', hint: '建築／敘事／NPC／道具班底' },
    ],
  },
];

export const MINECRAFT_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'minecraft',
    label: '伺服器',
    items: [
      { key: 'building', icon: '⌂', label: '建築', hint: 'Schematic 生成與派發' },
      { key: 'minecraft', icon: '⇄', label: '橋接', hint: 'MineMCP 探測與審計' },
    ],
  },
];

export const MONITOR_NAV_GROUPS: MonitorNavGroup[] = [
  ...CONSOLE_NAV_GROUPS,
  ...LINKIN_NAV_GROUPS,
  ...MINECRAFT_NAV_GROUPS,
];

/** 實驗室獨立活動，不進控制台／靈境側欄。 */
export const LAB_TAB: MonitorTabItem = { key: 'lab', icon: '✦', label: '實驗室' };

/** 全部（相容舊呼叫）。 */
export const MONITOR_TABS: MonitorTabItem[] = [
  ...MONITOR_SETUP_TABS,
  ...MONITOR_WORK_TABS,
  ...MONITOR_OBSERVE_TABS,
  ...MONITOR_SYSTEM_TABS,
  ...MONITOR_LINKIN_TABS,
  ...MONITOR_MINECRAFT_TABS,
  LAB_TAB,
];

/** @deprecated 使用 MONITOR_WORK_TABS */
export const MONITOR_PRIMARY_TABS = MONITOR_WORK_TABS;

/** @deprecated 使用 MONITOR_NAV_GROUPS */
export const MONITOR_MORE_TABS: MonitorTabItem[] = [
  ...MONITOR_OBSERVE_TABS,
  ...MONITOR_SYSTEM_TABS,
  LAB_TAB,
];

/** 舊分頁鍵 → 新分頁。 */
export const MONITOR_TAB_ALIASES: Record<string, MonitorTab> = {
  overview: 'live',
  balancer: 'live',
  task: 'tasks',
  dashboard: 'tasks',
  hub: 'ops',
  cloud: 'ops',
  checkpoints: 'ops',
  opc: 'metrics',
  dbpool: 'ops',
  routes: 'llm',
  mc: 'minecraft',
  minecraft_mcp: 'minecraft',
  studio_roles: 'studio',
  linkin_roles: 'studio',
  l0: 'memory',
  grill: 'agents',
};

const WORK_TAB_KEYS = new Set<string>(MONITOR_WORK_TABS.map((t) => t.key));
const LINKIN_TAB_KEYS = new Set<string>(MONITOR_LINKIN_TABS.map((t) => t.key));
const MINECRAFT_TAB_KEYS = new Set<string>(MONITOR_MINECRAFT_TABS.map((t) => t.key));
const CONSOLE_TAB_KEYS = new Set<string>([
  ...MONITOR_SETUP_TABS.map((t) => t.key),
  ...MONITOR_WORK_TABS.map((t) => t.key),
  ...MONITOR_OBSERVE_TABS.map((t) => t.key),
  ...MONITOR_SYSTEM_TABS.map((t) => t.key),
]);

/** 控制台頂欄五個主入口（靈境／Minecraft 不進此列）。 */
export const CONSOLE_CHROME_TABS: Array<{ key: MonitorTab; label: string; match: MonitorTab[] }> = [
  { key: 'live', label: '總覽', match: ['live', 'pipeline'] },
  { key: 'tasks', label: '新項', match: ['tasks'] },
  { key: 'models', label: '使用', match: ['models', 'metrics', 'feedback'] },
  { key: 'llm', label: '權限', match: ['llm', 'ops', 'memory'] },
  { key: 'agents', label: '角色', match: ['agents'] },
];

export function consoleChromeTabKey(tab: MonitorTab | 'traces'): MonitorTab | null {
  if (tab === 'traces') return 'tasks';
  return CONSOLE_CHROME_TABS.find((item) => item.match.includes(tab))?.key ?? null;
}

export const ACTIVITY_DEFAULT_TAB: Record<Exclude<ActivityKey, 'chat'>, MonitorTab | 'traces'> = {
  console: 'live',
  linkin: 'world',
  minecraft: 'building',
  lab: 'lab',
};
export function normalizeMonitorTab(tab: string | null | undefined): MonitorTab {
  if (!tab) return 'live';
  if (MONITOR_TABS.some((t) => t.key === tab)) return tab as MonitorTab;
  return MONITOR_TAB_ALIASES[tab] ?? 'live';
}

export function monitorTabLabel(tab: MonitorTab): string {
  return MONITOR_TABS.find((item) => item.key === tab)?.label ?? tab;
}

export function isMonitorMoreTab(tab: MonitorTab): boolean {
  return MONITOR_MORE_TABS.some((t) => t.key === tab);
}

export function isLinkinTab(tab: MonitorTab | string | null | undefined): boolean {
  return Boolean(tab && LINKIN_TAB_KEYS.has(tab));
}

export function isMinecraftTab(tab: MonitorTab | string | null | undefined): boolean {
  return Boolean(tab && MINECRAFT_TAB_KEYS.has(tab));
}

export function isConsoleTab(tab: MonitorTab | string | null | undefined): boolean {
  return Boolean(tab && CONSOLE_TAB_KEYS.has(tab));
}

export function resolveActivity(
  view: 'chat' | 'monitor' | 'traces',
  monitorTab: MonitorTab,
): ActivityKey {
  if (view === 'chat') return 'chat';
  if (view === 'traces') return 'console';
  if (monitorTab === 'lab') return 'lab';
  if (isMinecraftTab(monitorTab)) return 'minecraft';
  if (isLinkinTab(monitorTab)) return 'linkin';
  return 'console';
}
export function isWorkActivity(
  view: 'chat' | 'monitor' | 'traces',
  monitorTab: MonitorTab,
): boolean {
  return resolveActivity(view, monitorTab) === 'console';
}

export function navGroupsForActivity(activity: ActivityKey): MonitorNavGroup[] {
  if (activity === 'console') return CONSOLE_NAV_GROUPS;
  if (activity === 'linkin') return LINKIN_NAV_GROUPS;
  if (activity === 'minecraft') return MINECRAFT_NAV_GROUPS;
  return [];
}

export function navItemsForActivity(activity: ActivityKey): MonitorTabItem[] {
  if (activity === 'console') {
    return [...MONITOR_SETUP_TABS, ...MONITOR_WORK_TABS, ...MONITOR_OBSERVE_TABS, ...MONITOR_SYSTEM_TABS];
  }
  if (activity === 'linkin') return MONITOR_LINKIN_TABS;
  if (activity === 'minecraft') return MONITOR_MINECRAFT_TABS;
  return [];
}

export function activityTitle(activity: ActivityKey): string {
  if (activity === 'chat') return '對話';
  if (activity === 'lab') return '實驗室';
  if (activity === 'linkin') return '靈境';
  if (activity === 'minecraft') return 'Minecraft';
  return '控制台';
}
export function navGroupForTab(tab: ConsoleNavKey): MonitorNavGroup['id'] | null {
  return MONITOR_NAV_GROUPS.find((g) => g.items.some((i) => i.key === tab))?.id ?? null;
}

/** 跨頁麵包屑，例如「配置 → API 路由」。 */
export function navPathForTab(tab: ConsoleNavKey): string {
  const group = MONITOR_NAV_GROUPS.find((g) => g.items.some((i) => i.key === tab));
  const item = group?.items.find((i) => i.key === tab);
  if (!group || !item) return item?.label ?? String(tab);
  return `${group.label} → ${item.label}`;
}

/** 含活動名的跨活動路徑，例如「Minecraft → 橋接」。 */
export function activityNavPath(tab: ConsoleNavKey): string {
  if (tab === 'traces') return `${activityTitle('console')} → ${navPathForTab('traces')}`;
  const activity = resolveActivity('monitor', tab);
  const item =
    navItemsForActivity(activity).find((i) => i.key === tab) ??
    MONITOR_TABS.find((i) => i.key === tab);
  return `${activityTitle(activity)} → ${item?.label ?? String(tab)}`;
}
/** 頂欄路徑：配置 → API 路由（不含活動名前綴）。 */
export function consoleChromeLabel(
  view: 'chat' | 'monitor' | 'traces',
  monitorTab: MonitorTab,
  _labLabel?: string,
  traceTaskId?: string | null,
): string {
  if (view === 'chat') return '';
  if (view === 'traces') {
    const path = navPathForTab('traces');
    return traceTaskId ? `${path} · ${traceTaskId.slice(0, 8)}…` : path;
  }
  if (monitorTab === 'lab') return _labLabel ? `實驗室 · ${_labLabel}` : '實驗室';
  if (isMinecraftTab(monitorTab)) {
    return MONITOR_MINECRAFT_TABS.find((item) => item.key === monitorTab)?.label ?? monitorTab;
  }
  return navPathForTab(monitorTab);
}

export function isWorkTab(tab: MonitorTab): boolean {
  return WORK_TAB_KEYS.has(tab);
}
