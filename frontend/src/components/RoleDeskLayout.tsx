/**
 * 角色工作台骨架：標題列、指標帶、右側資訊欄。
 * 色彩沿用控制台既有語彙，只改結構。
 *
 * 第五輪重構：實作已拆至 ./roledesk/ 套件，此檔保留既有匯入路徑與公開 export。
 */
export { roleInitials } from './roledesk/shared';
export { RoleDeskHeader } from './roledesk/RoleDeskHeader';
export { RoleStatsStrip } from './roledesk/RoleStatsStrip';
export { OrgReportTree } from './roledesk/OrgReportTree';
export { TaskStatusBlock, TokenUsageBlock, CostDetailBlock, RdCell } from './roledesk/RoleTaskBlocks';
export { RoleMonitorBlock, EventTimelineBlock, L0ContextBlock } from './roledesk/RoleMonitorBlocks';
export { RoleRightPanel } from './roledesk/RoleRightPanel';
export type { RoleDeskTab } from './roledesk/types';
