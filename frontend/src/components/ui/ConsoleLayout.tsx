/**
 * 控制台共用版面元件 — 包裝 consoleLayout tokens，避免各面板重複 ad-hoc padding。
 *
 * 第九輪重構：實作已拆至 ./consolelayout/ 套件，此檔保留既有匯入路徑與全部公開 export。
 */
export { cn } from './consolelayout/cn';
export { PanelShell, ConsoleThreeColumn } from './consolelayout/Shell';
export {
  ConsoleLeftRail,
  ConsoleCenterColumn,
  ConsoleRightRail,
  ConsoleColumnScroll,
  ConsoleRailNav,
  PanelScroll,
} from './consolelayout/Rails';
export {
  ConsoleTabBody,
  ConsoleTabContent,
  PanelSection,
  SectionHeader,
  PanelAlert,
  PanelTabBar,
  ConsoleSection,
} from './consolelayout/Sections';
export {
  ConsoleGiantKpi,
  ConsolePlanChip,
  ConsoleSnippetList,
  KpiGrid,
  KpiGrid4,
  KpiGrid6,
  WarnBar,
  KpiCard,
} from './consolelayout/Kpi';
export {
  ConsoleCard,
  ConsoleCardHeader,
  ConsoleCardBody,
  ConsoleEmpty,
  ConsoleRdShell,
} from './consolelayout/Cards';
export { ConsoleSectionNav, ConsoleRdToolbar } from './consolelayout/SectionNav';
export { useSectionScrollSpy, useScrollToSection } from './consolelayout/hooks';
export { consoleLayout } from './consolelayout/tokens';
export type { SectionNavItem } from './consolelayout/types';
