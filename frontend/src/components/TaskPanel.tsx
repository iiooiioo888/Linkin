/** 任務介面面板（參考 PysdnOPC 任務列表風格）。
 *
 * 公司模式：角色流水線芯片（Manager → 執行角色 → Reviewer →
 * Synthesizer）+ 子項三欄（隊列／執行中／已完成）+ 事件時間軸。
 * 標準模式：階段進度 + 評分軌跡。
 *
 * 第八輪重構：實作已拆至 ./taskpanel/ 套件，此檔保留既有匯入路徑與公開 export。
 */
export { default } from './taskpanel/TaskPanel';
export { COMPANY_PHASES, OPC_PHASES, STANDARD_PHASES, phaseIndex } from './taskpanel/phases';
export { EVENT_LABELS, ITEM_STATUS_META, ROLE_LABELS, roleLabel } from './taskpanel/roleMeta';
export { RoleIcon } from './taskpanel/RoleIcon';
export { elapsed } from './taskpanel/time';
export type { RoleStatus } from './taskpanel/types';
