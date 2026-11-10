/**
 * 角色設定套件 barrel：維持原 RoleSettingsPanel 模組的公開 API。
 */
export { default } from './RoleSettingsPanel';
export { CreateRoleModal } from './CreateRoleModal';
export { draftFromAgent, draftToPayload } from './types';
export type { RoleSettingsDraft, RoleSettingsSection } from './types';
