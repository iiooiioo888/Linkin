/**
 * 角色設定表單：內建覆蓋 + 自定義角色建立／刪除／複製。
 *
 * 實作已拆至 ./role-settings/ 套件；此檔保留既有匯入路徑與公開 API。
 */
export { default, CreateRoleModal, draftFromAgent, draftToPayload } from './role-settings';
export type { RoleSettingsDraft, RoleSettingsSection } from './role-settings';
