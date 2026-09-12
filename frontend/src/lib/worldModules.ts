/**
 * 世界／整合模組目錄（前端契約）。
 *
 * 與後端 GET /modules 對齊。啟動時 hydrate；離線或 GitHub Pages 用內建
 * Minecraft 目錄。新模組：後端 register_module + 前端 registerModulePages。
 * 不可 import monitorTabs（避免循環依賴）。
 */
import { useEffect, useState } from 'react';
import { fetchModuleCatalog, type ModuleCatalogItem } from '../api/modules';

export type ModuleIconKey = 'minecraft' | 'generic';

export type ModuleRosterKind = 'agents' | 'tasks';

export type ModuleNavItem = {
  key: string;
  icon: string;
  label: string;
  hint?: string;
  capability?: string;
  roster?: ModuleRosterKind;
};
export type ModuleNavGroup = { id: string; label: string; items: ModuleNavItem[] };

export type WorldModuleCapability = {
  id: string;
  title: string;
  description: string;
  api_prefix: string;
  routes: string[];
};

export type WorldModulePage = {
  key: string;
  group: string;
  group_label?: string;
  icon: string;
  label: string;
  hint?: string;
  capability?: string | null;
  api_prefix: string;
  routes: string[];
};

export type WorldModuleSpec = {
  id: string;
  title: string;
  description: string;
  version: string;
  kind: string;
  icon: ModuleIconKey;
  defaultPage: string;
  enabled: boolean;
  apiPrefix: string;
  gatewayPrefix: string;
  capabilities: WorldModuleCapability[];
  navGroups: ModuleNavGroup[];
  pages?: WorldModulePage[];
  pageAliases?: Record<string, string>;
};

const MINECRAFT_NAV: ModuleNavGroup[] = [
  {
    id: 'monitor',
    label: '總覽／監控',
    items: [
      { key: 'monitor', icon: '◎', label: '監控總覽', hint: 'KPI、管線、橋接與 AI 可見事件', capability: 'monitor' },
      { key: 'map_monitor', icon: '◇', label: '地圖監控', hint: '地圖計畫與落地狀態', capability: 'monitor' },
      { key: 'npc_monitor', icon: '☺', label: 'NPC 監控', hint: '待落地／已落地／失敗', capability: 'monitor' },
      { key: 'quest_item_monitor', icon: '◆', label: '任務／道具監控', hint: '世界意圖狀態帶', capability: 'monitor' },
      { key: 'build_monitor', icon: '⌂', label: '建築落地監控', hint: 'build-brief 任務與方塊', capability: 'monitor' },
      { key: 'bridge_monitor', icon: '⇄', label: '橋接健康', hint: 'MineMCP 連線與錯誤', capability: 'bridge' },
    ],
  },
  {
    id: 'narrative_group',
    label: '敘事／RPG',
    items: [
      { key: 'narrative', icon: '✎', label: '敘事工作區', hint: 'Phase 0–5 一鍵管線', capability: 'content' },
    ],
  },
  {
    id: 'world_build',
    label: '世界與建築',
    items: [
      { key: 'building', icon: '⌂', label: '建築', hint: 'Schematic 生成與派發', capability: 'building' },
      { key: 'map_plan', icon: '◫', label: '地圖計畫', hint: '區域地圖生成／預覽／落地', capability: 'content' },
      { key: 'minecraft', icon: '⇄', label: '橋接', hint: 'MineMCP 探測與審計', capability: 'bridge' },
    ],
  },
  {
    id: 'entities',
    label: '實體',
    items: [
      { key: 'npcs', icon: '☺', label: 'NPC', hint: '角色卡與對話', capability: 'content' },
      { key: 'quests', icon: '⚑', label: '任務', hint: '主線／支線／日常', capability: 'content' },
      { key: 'items', icon: '◆', label: '道具', hint: '稀有度平衡', capability: 'content' },
    ],
  },
  {
    id: 'plugins',
    label: '插件／地圖',
    items: [
      {
        key: 'plugin-hub',
        icon: '⚡',
        label: '插件中心',
        hint: 'Dynmap／BlueMap／Squaremap 等目錄與連線狀態',
        capability: 'plugins',
      },
      {
        key: 'server-map',
        icon: '🗺',
        label: '伺服器地圖',
        hint: '內嵌網頁地圖（Dynmap／BlueMap／Squaremap）',
        capability: 'plugins',
      },
    ],
  },
  {
    id: 'admin_group',
    label: '憲章／工作室／管理',
    items: [
      { key: 'world', icon: '✧', label: '世界觀', hint: '憲法與陣營', capability: 'worldview' },
      { key: 'studio', icon: '◈', label: '工作室角色', hint: '建築／敘事班底', roster: 'agents' },
      { key: 'admin', icon: '⌘', label: 'Admin', hint: '健康、批准、巡檢、指令', capability: 'admin' },
    ],
  },
];

export const BUILTIN_WORLD_MODULES: WorldModuleSpec[] = [
  {
    id: 'minecraft',
    title: 'Minecraft',
    description: '靈境世界觀、伺服器 Admin、內容工作室與 MineMCP 橋接',
    version: '1.0.0',
    kind: 'world',
    icon: 'minecraft',
    defaultPage: 'monitor',
    enabled: true,
    apiPrefix: '/linkin',
    gatewayPrefix: '/modules/minecraft/api',
    capabilities: [
      {
        id: 'worldview',
        title: '世界觀',
        description: '憲法、陣營、事件與總覽',
        api_prefix: '/linkin',
        routes: ['/constitution', '/overview', '/events'],
      },
      {
        id: 'content',
        title: '世界內容',
        description: 'NPC、任務、道具',
        api_prefix: '/linkin',
        routes: ['/npcs', '/quests', '/items', '/narrative/workspaces'],
      },
      {
        id: 'admin',
        title: 'Admin',
        description: '遊戲指令與伺服器運維',
        api_prefix: '/linkin',
        routes: ['/admin/execute', '/server/health', '/server/approvals'],
      },
      {
        id: 'building',
        title: '建築',
        description: 'Schematic 生成、匯入與派發',
        api_prefix: '/linkin',
        routes: ['/buildings', '/buildings/generate', '/buildings/import'],
      },
      {
        id: 'bridge',
        title: '橋接',
        description: 'MineMCP 狀態、探測與護欄呼叫',
        api_prefix: '/linkin',
        routes: ['/minecraft/status', '/minecraft/probe', '/minecraft/call'],
      },
      {
        id: 'monitor',
        title: '監控',
        description: 'Minecraft 運維監控與 AI 可觀測性',
        api_prefix: '/linkin',
        routes: [
          '/minecraft/monitor/summary',
          '/minecraft/ai/snapshot',
          '/minecraft/ai/events',
          '/minecraft/ai/context',
          '/map/plans',
        ],
      },
      {
        id: 'plugins',
        title: '插件／地圖',
        description: '第三方插件目錄、地圖 URL 設定與內嵌檢視',
        api_prefix: '/linkin',
        routes: ['/minecraft/plugins/catalog', '/minecraft/plugins/settings', '/minecraft/plugins/{id}/probe'],
      },
    ],
    navGroups: MINECRAFT_NAV,
    pageAliases: {
      mc: 'minecraft',
      minecraft_mcp: 'minecraft',
      bridge: 'minecraft',
      overview: 'monitor',
      monitor_hub: 'monitor',
      map: 'map_monitor',
      studio_roles: 'studio',
      linkin_roles: 'studio',
      server: 'admin',
      ops_admin: 'admin',
      plugins: 'plugin-hub',
      plugin_center: 'plugin-hub',
      server_map: 'server-map',
      dynmap: 'server-map',
    },
  },
];

/** 舊 hash／書籤別名 → 模組頁鍵。控制台別名不放這裡。 */
export const MODULE_PAGE_ALIASES: Record<string, string> = {
  mc: 'minecraft',
  minecraft_mcp: 'minecraft',
  bridge: 'minecraft',
  overview: 'monitor',
  monitor_hub: 'monitor',
  map: 'map_monitor',
  studio_roles: 'studio',
  linkin_roles: 'studio',
  server: 'admin',
  ops_admin: 'admin',
  plugins: 'plugin-hub',
  plugin_center: 'plugin-hub',
  server_map: 'server-map',
  dynmap: 'server-map',
};

const EXTRA_MODULES: WorldModuleSpec[] = [];
const listeners = new Set<() => void>();
let remoteSpecs: WorldModuleSpec[] = [];

function asIcon(raw: string | undefined): ModuleIconKey {
  return raw === 'minecraft' ? 'minecraft' : 'generic';
}

export function catalogToSpec(item: ModuleCatalogItem): WorldModuleSpec {
  return {
    id: item.id,
    title: item.title,
    description: item.description,
    version: item.version || '1.0.0',
    kind: item.kind || 'world',
    icon: asIcon(item.icon),
    defaultPage: item.default_page || '',
    enabled: item.enabled !== false,
    apiPrefix: item.api_prefix || '',
    gatewayPrefix: item.gateway_prefix || (item.id ? `/modules/${item.id}/api` : ''),
    capabilities: item.capabilities ?? [],
    navGroups: (item.nav_groups ?? []).map((group) => ({
      id: group.id,
      label: group.label,
      items: group.items.map((nav) => ({
        key: nav.key,
        icon: nav.icon,
        label: nav.label,
        hint: nav.hint,
        capability: nav.capability,
        roster: nav.roster === 'agents' || nav.roster === 'tasks' ? nav.roster : undefined,
      })),
    })),
    pages: item.pages,
    pageAliases: item.page_aliases,
  };
}

function mergeSpec(base: WorldModuleSpec, overlay: WorldModuleSpec): WorldModuleSpec {
  return {
    ...base,
    ...overlay,
    capabilities: overlay.capabilities.length ? overlay.capabilities : base.capabilities,
    navGroups: overlay.navGroups.length ? overlay.navGroups : base.navGroups,
    pages: overlay.pages?.length ? overlay.pages : base.pages,
    defaultPage: overlay.defaultPage || base.defaultPage,
    apiPrefix: overlay.apiPrefix || base.apiPrefix,
    gatewayPrefix: overlay.gatewayPrefix || base.gatewayPrefix,
    pageAliases: overlay.pageAliases && Object.keys(overlay.pageAliases).length
      ? overlay.pageAliases
      : base.pageAliases,
  };
}

function notify(): void {
  listeners.forEach((fn) => fn());
}

export function subscribeWorldModules(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function applyRemoteModules(items: WorldModuleSpec[]): void {
  remoteSpecs = items;
  notify();
}

export function listWorldModules(): WorldModuleSpec[] {
  const byId = new Map<string, WorldModuleSpec>();
  for (const spec of [...BUILTIN_WORLD_MODULES, ...EXTRA_MODULES]) {
    if (!spec.enabled) continue;
    byId.set(spec.id, spec);
  }
  for (const spec of remoteSpecs) {
    if (!spec.enabled) {
      byId.delete(spec.id);
      continue;
    }
    const prev = byId.get(spec.id);
    byId.set(spec.id, prev ? mergeSpec(prev, spec) : spec);
  }
  return [...byId.values()];
}

export function getWorldModule(id: string | null | undefined): WorldModuleSpec | null {
  if (!id) return null;
  return listWorldModules().find((item) => item.id === id) ?? null;
}

export function pagesOfModule(id: string): string[] {
  const spec = getWorldModule(id);
  if (!spec) return [];
  if (spec.pages?.length) return spec.pages.map((page) => page.key);
  return spec.navGroups.flatMap((group: ModuleNavGroup) => group.items.map((item: ModuleNavItem) => item.key));
}

export function moduleIdForTab(tab: string | null | undefined): string | null {
  if (!tab) return null;
  for (const spec of listWorldModules()) {
    if (pagesOfModule(spec.id).includes(tab)) return spec.id;
    if (spec.navGroups.some((group) => group.items.some((item) => item.key === tab))) {
      return spec.id;
    }
  }
  return null;
}

export function isModuleTab(tab: string | null | undefined): boolean {
  return moduleIdForTab(tab) !== null;
}

export function isModuleActivity(activity: string | null | undefined): boolean {
  return Boolean(activity && getWorldModule(activity));
}

/** 舊活動鍵：靈境已併入 Minecraft 模組。 */
export function normalizeActivityAlias(activity: string | null | undefined): string | null {
  if (!activity) return null;
  if (activity === 'linkin') return 'minecraft';
  return activity;
}

function aliasMap(): Record<string, string> {
  const out: Record<string, string> = { ...MODULE_PAGE_ALIASES };
  for (const spec of listWorldModules()) {
    for (const [from, to] of Object.entries(spec.pageAliases ?? {})) {
      out[from] = to;
    }
  }
  return out;
}

export function resolveModulePage(tab: string | null | undefined): string | null {
  if (!tab) return null;
  const aliased = aliasMap()[tab] ?? tab;
  return moduleIdForTab(aliased) ? aliased : null;
}

export function rosterKindForTab(tab: string | null | undefined): ModuleRosterKind | null {
  if (!tab) return null;
  const spec = getWorldModule(moduleIdForTab(tab));
  if (!spec) return null;
  for (const group of spec.navGroups) {
    const item = group.items.find((nav) => nav.key === tab);
    if (item?.roster) return item.roster;
  }
  return null;
}

export function isMinecraftTab(tab: string | null | undefined): boolean {
  return moduleIdForTab(tab) === 'minecraft';
}

export function hashPageForTab(tab: string, moduleId: string): string {
  if (moduleId === 'minecraft' && tab === 'minecraft') return 'bridge';
  return tab;
}

export function tabForModulePage(page: string | null | undefined): string | null {
  if (!page) return null;
  return resolveModulePage(page) ?? page;
}

export async function hydrateWorldModules(): Promise<WorldModuleSpec[]> {
  try {
    const items = await fetchModuleCatalog();
    applyRemoteModules(items.filter((item) => item.enabled !== false).map(catalogToSpec));
  } catch {
    // 離線／Pages：保留內建目錄
  }
  return listWorldModules();
}

export function useWorldModules(): WorldModuleSpec[] {
  const [mods, setMods] = useState(listWorldModules);
  useEffect(() => subscribeWorldModules(() => setMods(listWorldModules())), []);
  return mods;
}
