/**
 * Mobile Lite Shell vs Desktop Full Console — 全站呈現策略（單一資料源）。
 *
 * <768px：底部主 Tab＝工作／觀測／更多；後端能力不裁切。
 * ≥768px：完整 Agent Desk 密度與三欄布局。
 */
import type { MonitorTab } from '../components/AppShell';
import type { ActivityKey, DeskActivityKey, MonitorNavGroup } from './monitorTabs';

export const MOBILE_SHELL_MAX_WIDTH_PX = 767;
export const MOBILE_SHELL_MEDIA = `(max-width: ${MOBILE_SHELL_MAX_WIDTH_PX}px)`;
export const DESKTOP_SHELL_MEDIA = '(min-width: 768px)';

export type ShellMode = 'lite' | 'full';

/** 手機底部主 Tab：工作／觀測（計算等進「更多」） */
export const MOBILE_PRIMARY_ACTIVITIES: ReadonlyArray<DeskActivityKey> = [
  'work',
  'observe',
];

/** 「更多」內含：計算／供給／資產／世界／設定 */
export const MOBILE_MORE_ACTIVITIES: ReadonlyArray<DeskActivityKey> = [
  'compute',
  'supply',
  'assets',
  'world',
  'settings',
];

/** 底部 Tab 直達 + 預設可見的監控分頁（相容舊呼叫） */
export const MOBILE_LITE_PRIMARY_TABS: ReadonlySet<MonitorTab> = new Set([
  'live',
  'tasks',
  'models',
]);

/** 可經「更多／進階」進入 */
export const MOBILE_LITE_ADVANCED_TABS: ReadonlySet<MonitorTab> = new Set([
  'agents',
  'feedback',
  'metrics',
  'llm',
  'memory',
  'context',
  'integrations',
  'skills',
  'ops',
  'lab',
  'exec',
  'quota',
  'health',
  'approvals',
]);

/** 預設隱藏完整控制 chrome */
export const MOBILE_DESKTOP_ONLY_PANELS: ReadonlySet<MonitorTab> = new Set([
  'skills',
  'ops',
  'llm',
  'memory',
  'context',
  'integrations',
  'metrics',
  'feedback',
  'exec',
  'quota',
]);

/** SidePanel 主導航保留的分頁鍵（觀測／工作精簡） */
export const MOBILE_LITE_NAV_PRIMARY_KEYS: ReadonlySet<string> = new Set([
  'live',
  'tasks',
  'chat',
  'agents',
]);

/** Minecraft 模組手機側欄預設可見頁 */
export const MOBILE_MINECRAFT_PRIMARY_KEYS: ReadonlySet<string> = new Set([
  'monitor',
  'narrative',
  'player_presence',
  'bridge_monitor',
]);

const MOBILE_MODULE_PRIMARY_KEYS: Partial<Record<string, ReadonlySet<string>>> = {
  minecraft: MOBILE_MINECRAFT_PRIMARY_KEYS,
};

function primaryKeysForActivity(activity: ActivityKey | undefined): ReadonlySet<string> {
  if (activity === 'world' || activity === 'minecraft') {
    return MOBILE_MINECRAFT_PRIMARY_KEYS;
  }
  if (activity && MOBILE_MODULE_PRIMARY_KEYS[activity]) {
    return MOBILE_MODULE_PRIMARY_KEYS[activity]!;
  }
  if (activity === 'work') return new Set(['chat', 'tasks', 'traces', 'company']);
  if (activity === 'observe') return new Set(['live', 'agents', 'feedback']);
  if (activity === 'compute') return new Set(['models', 'exec']);
  if (activity === 'supply') return new Set(['quota', 'health']);
  if (activity === 'assets') return new Set(['context', 'memory']);
  if (activity === 'settings') return new Set(['llm', 'skills', 'ops']);
  return MOBILE_LITE_NAV_PRIMARY_KEYS;
}

export function shellModeFromWidth(width: number): ShellMode {
  return width <= MOBILE_SHELL_MAX_WIDTH_PX ? 'lite' : 'full';
}

export function isMobileLitePrimaryTab(tab: MonitorTab | string): boolean {
  return MOBILE_LITE_PRIMARY_TABS.has(tab as MonitorTab);
}

export function isMobileDesktopOnlyPanel(tab: MonitorTab | string): boolean {
  return MOBILE_DESKTOP_ONLY_PANELS.has(tab as MonitorTab);
}

export function partitionNavGroupsForMobileLite(
  groups: MonitorNavGroup[],
  activity?: ActivityKey,
): {
  primary: MonitorNavGroup[];
  advanced: MonitorNavGroup[];
} {
  const primaryKeys = primaryKeysForActivity(activity);
  const primary: MonitorNavGroup[] = [];
  const advancedItems: MonitorNavGroup['items'] = [];

  for (const group of groups) {
    const primaryItems = group.items.filter((item) => primaryKeys.has(String(item.key)));
    const restItems = group.items.filter((item) => !primaryKeys.has(String(item.key)));

    if (primaryItems.length > 0) {
      primary.push({ ...group, items: primaryItems });
    }
    advancedItems.push(...restItems);
  }

  const advanced: MonitorNavGroup[] =
    advancedItems.length > 0
      ? [
          {
            id: 'mobile-advanced',
            label: 'mobile-advanced',
            items: advancedItems,
          },
        ]
      : [];

  return { primary, advanced };
}
