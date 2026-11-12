/**
 * 頂層活動（Desk）資料、舊活動別名與活動判斷 helpers。
 */
import type { MonitorTab } from '../../components/AppShell';
import { getWorldModule, normalizeActivityAlias as normalizeModuleActivityAlias } from '../worldModules';
import type { ActivityKey, DeskActivityKey } from './types';

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
};

export function activityTitle(activity: ActivityKey): string {
  const resolved = normalizeDeskActivity(activity);
  const found = DESK_ACTIVITIES.find((a) => a.key === resolved);
  if (found) return found.label;
  const spec = getWorldModule(normalizeModuleActivityAlias(String(activity)) ?? String(activity));
  return spec?.title ?? '模組';
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
