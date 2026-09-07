/**
 * 監控中心分頁定義（單一資料源）。
 *
 * 左側三層：
 *   ActivityBar（對話 / 控制台 / 實驗室）
 *   → SidePanel 分組功能
 *   → 上下文清單（會話／名冊／軌跡）
 */
import type { MonitorTab } from '../components/AppShell';

export type ActivityKey = 'chat' | 'console' | 'lab';

export type ConsoleNavKey = MonitorTab | 'traces';

export type MonitorTabItem = { key: MonitorTab; icon: string; label: string };
export type ConsoleNavItem = { key: ConsoleNavKey; icon: string; label: string; hint?: string };

export type MonitorNavGroup = {
  id: 'setup' | 'execute' | 'observe' | 'system' | 'linkin';
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
  { key: 'memory', icon: '◌', label: '記憶' },
  { key: 'ops', icon: '⚙', label: '基礎設施' },
];

export const MONITOR_LINKIN_TABS: MonitorTabItem[] = [
  { key: 'world', icon: '✧', label: '世界觀' },
  { key: 'npcs', icon: '☺', label: 'NPC' },
  { key: 'quests', icon: '⚑', label: '任務' },
  { key: 'building', icon: '⌂', label: '建築' },
  { key: 'items', icon: '◆', label: '道具' },
  { key: 'minecraft', icon: '▣', label: 'Minecraft' },
];

export const MONITOR_NAV_GROUPS: MonitorNavGroup[] = [
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
      { key: 'tasks', icon: '▣', label: '任務', hint: '佇列與進度' },
      { key: 'agents', icon: '◈', label: '角色', hint: '模型／Token／工作台' },
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
      { key: 'memory', icon: '◌', label: '記憶', hint: '向量檢索' },
      { key: 'ops', icon: '⚙', label: '基礎設施', hint: 'Hub／雲／檢查點／連線池' },
    ],
  },
  {
    id: 'linkin',
    label: '靈境',
    items: [
      { key: 'world', icon: '✧', label: '世界觀', hint: '憲法與陣營' },
      { key: 'npcs', icon: '☺', label: 'NPC', hint: '角色卡與對話' },
      { key: 'quests', icon: '⚑', label: '任務', hint: '主線／支線／日常' },
      { key: 'building', icon: '⌂', label: '建築', hint: '風格與方塊上限' },
      { key: 'items', icon: '◆', label: '道具', hint: '稀有度平衡' },
      { key: 'minecraft', icon: '▣', label: 'Minecraft', hint: 'MineMCP 橋接與審計' },
    ],
  },
];

/** 實驗室獨立活動，不進控制台側欄。 */
export const LAB_TAB: MonitorTabItem = { key: 'lab', icon: '✦', label: '實驗室' };

/** 全部（相容舊呼叫）。 */
export const MONITOR_TABS: MonitorTabItem[] = [
  ...MONITOR_SETUP_TABS,
  ...MONITOR_WORK_TABS,
  ...MONITOR_OBSERVE_TABS,
  ...MONITOR_SYSTEM_TABS,
  ...MONITOR_LINKIN_TABS,
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
};

const WORK_TAB_KEYS = new Set<string>(MONITOR_WORK_TABS.map((t) => t.key));

export const ACTIVITY_DEFAULT_TAB: Record<Exclude<ActivityKey, 'chat'>, MonitorTab | 'traces'> = {
  console: 'live',
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

export function resolveActivity(
  view: 'chat' | 'monitor' | 'traces',
  monitorTab: MonitorTab,
): ActivityKey {
  if (view === 'chat') return 'chat';
  if (view === 'traces') return 'console';
  if (monitorTab === 'lab') return 'lab';
  return 'console';
}

export function isWorkActivity(
  view: 'chat' | 'monitor' | 'traces',
  monitorTab: MonitorTab,
): boolean {
  return resolveActivity(view, monitorTab) === 'console';
}

export function navItemsForActivity(activity: ActivityKey): MonitorTabItem[] {
  if (activity === 'console') return MONITOR_TABS.filter((t) => t.key !== 'lab');
  return [];
}

export function activityTitle(activity: ActivityKey): string {
  if (activity === 'chat') return '對話';
  if (activity === 'lab') return '實驗室';
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

/** 頂欄：控制台 · 配置 → API 路由 */
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
  return navPathForTab(monitorTab);
}

export function isWorkTab(tab: MonitorTab): boolean {
  return WORK_TAB_KEYS.has(tab);
}
