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
    id: 'world',
    label: '世界',
    items: [
      { key: 'world', icon: '✧', label: '世界觀', hint: '憲法與陣營', capability: 'worldview' },
      { key: 'npcs', icon: '☺', label: 'NPC', hint: '角色卡與對話', capability: 'content' },
      { key: 'quests', icon: '⚑', label: '任務', hint: '主線／支線／日常', capability: 'content' },
      { key: 'items', icon: '◆', label: '道具', hint: '稀有度平衡', capability: 'content' },
    ],
  },
  {
    id: 'studio',
    label: '工作室',
    items: [{ key: 'studio', icon: '◈', label: '工作室角色', hint: '建築／敘事／NPC／道具班底', roster: 'agents' }],
  },
  {
    id: 'server',
    label: '伺服器',
    items: [
      { key: 'admin', icon: '⌘', label: 'Admin', hint: '健康、批准、巡檢、指令', capability: 'admin' },
      { key: 'building', icon: '⌂', label: '建築', hint: 'Schematic 生成與派發', capability: 'building' },
      { key: 'minecraft', icon: '⇄', label: '橋接', hint: 'MineMCP 探測與審計', capability: 'bridge' },
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
    defaultPage: 'world',
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
        routes: ['/npcs', '/quests', '/items'],
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
    ],
    navGroups: MINECRAFT_NAV,
    pageAliases: {
      mc: 'minecraft',
      minecraft_mcp: 'minecraft',
      bridge: 'minecraft',
      studio_roles: 'studio',
      linkin_roles: 'studio',
      server: 'admin',
      ops_admin: 'admin',
    },
  },
];

/** 舊 hash／書籤別名 → 模組頁鍵。控制台別名不放這裡。 */
export const MODULE_PAGE_ALIASES: Record<string, string> = {
  mc: 'minecraft',
  minecraft_mcp: 'minecraft',
  bridge: 'minecraft',
  studio_roles: 'studio',
  linkin_roles: 'studio',
  server: 'admin',
  ops_admin: 'admin',
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
