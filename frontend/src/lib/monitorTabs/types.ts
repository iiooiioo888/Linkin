/**
 * 導航型別：活動／側欄可點鍵／分組與項目。
 */
import type { MonitorTab } from '../../components/AppShell';

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
  /** 世界模組導覽項所屬模組（同名 page key 如 monitor 須帶上）。 */
  worldModuleId?: string;
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
