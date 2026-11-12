/**
 * RoleV3Desk — 角色監控三欄桌面（216 / 1fr / 304）。
 * 對齊 docs/design/monitor-dashboard-v3.html 與 SystemMetricsPanel 結構。
 *
 * 第十一輪重構：實作已拆至 ./roledesk-v3/ 套件，此檔保留既有匯入路徑與公開 export。
 */
export { default } from './roledesk-v3/RoleV3Desk';
export type { RoleV3DeskProps } from './roledesk-v3/types';
