/**
 * Minecraft 模組頁面註冊。世界觀／Admin／內容／建築／橋接都在本目錄，
 * 控制台不再 switch 這些分頁。
 */
import { wrapPanel } from '../wrapPanel';
import { registerModulePages } from '../pageRegistry';

export function registerMinecraftModule(): void {
  registerModulePages('minecraft', {
    world: wrapPanel(() => import('./WorldConstitutionPanel')),
    npcs: wrapPanel(() => import('./NpcManagerPanel')),
    quests: wrapPanel(() => import('./QuestPanel')),
    narrative: wrapPanel(() => import('./NarrativeWorkspacePanel')),
    items: wrapPanel(() => import('./ItemPanel')),
    studio: () => import('./StudioPage'),
    admin: wrapPanel(() => import('./AdminPanel')),
    building: wrapPanel(() => import('./BuildPanel')),
    minecraft: wrapPanel(() => import('./MinecraftBridgePanel')),
  });
}
