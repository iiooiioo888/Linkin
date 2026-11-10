import type { ConsoleNavKey } from '../lib/monitorTabs';
import type { MonitorTab } from './AppShell';

/** 側欄點選：必須使用被點項目的 `worldModuleId`，不可用 key 全域 find（monitor 等重複鍵）。 */
export function sidePanelMonitorPick(
  key: ConsoleNavKey,
  clickedWorldModuleId: string | undefined,
): { tab: MonitorTab; worldModuleId: string | null } {
  return {
    tab: key as MonitorTab,
    worldModuleId: clickedWorldModuleId ?? null,
  };
}
