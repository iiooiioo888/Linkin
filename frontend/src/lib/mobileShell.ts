/**
 * Mobile Lite Shell vs Desktop Full Console — 全站呈現策略（單一資料源）。
 *
 * <768px：精簡殼層（底部 Tab、摘要卡片、進階入口）；後端能力不裁切。
 * ≥768px：完整控制台密度與三欄布局。
 */
import type { MonitorTab } from '../components/AppShell';
import type { ActivityKey } from './monitorTabs';
import type { MonitorNavGroup } from './monitorTabs';

export const MOBILE_SHELL_MAX_WIDTH_PX = 767;
export const MOBILE_SHELL_MEDIA = `(max-width: ${MOBILE_SHELL_MAX_WIDTH_PX}px)`;
export const DESKTOP_SHELL_MEDIA = '(min-width: 768px)';

export type ShellMode = 'lite' | 'full';

/** 底部 Tab 直達 + 預設可見的監控分頁 */
export const MOBILE_LITE_PRIMARY_TABS: ReadonlySet<MonitorTab> = new Set([
  'live',
  'tasks',
  'models',
]);

/** 可經「更多／進階」進入，但預設以摘要或 Desktop 提示呈現 */
export const MOBILE_LITE_ADVANCED_TABS: ReadonlySet<MonitorTab> = new Set([
  'agents',
  'pipeline',
  'feedback',
  'metrics',
  'llm',
  'memory',
  'context',
  'integrations',
  'skills',
  'ops',
  'lab',
]);

/** 預設隱藏完整控制 chrome，需展開或改用桌面 */
export const MOBILE_DESKTOP_ONLY_PANELS: ReadonlySet<MonitorTab> = new Set([
  'skills',
  'ops',
  'llm',
  'memory',
  'context',
  'integrations',
  'metrics',
  'feedback',
  'pipeline',
]);

/** SidePanel 主導航保留的分頁鍵 */
export const MOBILE_LITE_NAV_PRIMARY_KEYS: ReadonlySet<string> = new Set([
  'live',
  'tasks',
  'models',
]);

/** Minecraft 模組手機側欄預設可見頁（其餘收進「進階」）。 */
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
  if (activity && MOBILE_MODULE_PRIMARY_KEYS[activity]) {
    return MOBILE_MODULE_PRIMARY_KEYS[activity]!;
  }
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
