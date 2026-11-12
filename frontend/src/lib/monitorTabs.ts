/**
 * Agent Desk 導航（Phase1）— 頂層活動＋側欄樹單一資料源。
 *
 * 頂層：工作／觀測／計算／供給／資產／世界／設定
 * 舊活動別名（chat／console／lab／company）仍可解析，對照至少一版。
 *
 * 第十輪重構：實作已拆至 ./monitorTabs/* 子模組，此檔保留既有 import 路徑與
 * 完全相同的公開 export 集合（export *）。
 */
export * from './monitorTabs/types';
export * from './monitorTabs/activity';
export * from './monitorTabs/tabs';
export * from './monitorTabs/tabAliases';
export * from './monitorTabs/navGroups';
export * from './monitorTabs/navHelpers';
export * from './monitorTabs/worldModuleBridge';
