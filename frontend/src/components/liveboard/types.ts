/**
 * LiveBoard 對外型別：密度（整頁／dock）與導覽 callback。
 */
import type { LabSubTab } from '../../lib/labTabs';
import type { MonitorTab } from '../AppShell';

export type LiveBoardDensity = 'page' | 'dock';

export interface LiveBoardNav {
  onOpenTab?: (tab: MonitorTab) => void;
  onOpenLab?: (sub: LabSubTab) => void;
  onOpenTraces?: () => void;
  onOpenAgent?: (id: string) => void;
}
