/**
 * Minecraft 模組頁面註冊。世界觀／Admin／內容／建築／橋接都在本目錄，
 * 控制台不再 switch 這些分頁。
 */
import { wrapPanel } from '../wrapPanel';
import { registerModulePages } from '../pageRegistry';

export function registerMinecraftModule(): void {
  registerModulePages('minecraft', {
    monitor: wrapPanel(() => import('./MonitorHubPanel')),
    map_monitor: wrapPanel(() => import('./MapMonitorPanel')),
    npc_monitor: wrapPanel(() => import('./NpcMonitorPanel')),
    quest_item_monitor: wrapPanel(() => import('./QuestItemMonitorPanel')),
    build_monitor: wrapPanel(() => import('./BuildMonitorPanel')),
    bridge_monitor: wrapPanel(() => import('./BridgeMonitorPanel')),
    map_plan: wrapPanel(() => import('./MapPlanPanel')),
    'layout-preview': wrapPanel(() => import('./LayoutPreviewPanel')),
    world: wrapPanel(() => import('./WorldConstitutionPanel')),
    npcs: wrapPanel(() => import('./NpcManagerPanel')),
    quests: wrapPanel(() => import('./QuestPanel')),
    narrative: wrapPanel(() => import('./NarrativeWorkspacePanel')),
    items: wrapPanel(() => import('./ItemPanel')),
    studio: () => import('./StudioPage'),
    admin: wrapPanel(() => import('./AdminPanel')),
    building: wrapPanel(() => import('./BuildPanel')),
    minecraft: wrapPanel(() => import('./MinecraftBridgePanel')),
    'plugin-hub': wrapPanel(() => import('./PluginHubPanel')),
    'server-map': wrapPanel(() => import('./ServerMapPanel')),
  });
}
