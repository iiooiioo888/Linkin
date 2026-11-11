/**
 * 世界／整合模組目錄（前端契約）。
 *
 * 與後端 GET /modules 對齊。啟動時 hydrate；離線或 GitHub Pages 用內建
 * 模組目錄。新模組：後端 register_module + 前端 registerModulePages。
 * 不可 import monitorTabs（避免循環依賴）。
 */
import { useEffect, useState } from 'react';
import { fetchModuleCatalog, type ModuleCatalogItem } from '../api/modules';
import { hasModulePage } from '../modules/pageRegistry';

export type ModuleIconKey = 'generic';

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

/** 內建模組目錄為空：media-vault／local-video-studio 由 GET /modules hydrate。 */
export const BUILTIN_WORLD_MODULES: WorldModuleSpec[] = [];

/** 舊 hash／書籤別名 → 模組頁鍵。控制台別名不放這裡。 */
export const MODULE_PAGE_ALIASES: Record<string, string> = {};

const EXTRA_MODULES: WorldModuleSpec[] = [];
const listeners = new Set<() => void>();
let remoteSpecs: WorldModuleSpec[] = [];

function asIcon(_raw: string | undefined): ModuleIconKey {
  return 'generic';
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
  const keys = new Set<string>();
  if (spec.pages?.length) {
    spec.pages.forEach((page) => keys.add(page.key));
  } else {
    spec.navGroups.forEach((group: ModuleNavGroup) => {
      group.items.forEach((item: ModuleNavItem) => keys.add(item.key));
    });
  }
  Object.values(spec.pageAliases ?? {}).forEach((target) => keys.add(target));
  return [...keys];
}

function aliasMapForModule(moduleId: string): Record<string, string> {
  const out: Record<string, string> = {};
  const spec = getWorldModule(moduleId);
  for (const [from, to] of Object.entries(spec?.pageAliases ?? {})) {
    out[from] = to;
  }
  return out;
}

/** 模組是否擁有此頁（目錄、導覽或前端頁面註冊）。 */
export function moduleOwnsPage(moduleId: string, page: string | null | undefined): boolean {
  if (!page) return false;
  const aliased = aliasMapForModule(moduleId)[page] ?? page;
  if (pagesOfModule(moduleId).includes(aliased)) return true;
  return hasModulePage(moduleId, aliased);
}

/** 在指定模組命名空間內解析 hash 頁名（別名、預設頁、僅註冊的前端頁）。 */
export function resolvePageForModule(moduleId: string, rawPage: string | null | undefined): string {
  const spec = getWorldModule(moduleId);
  const seed = rawPage?.trim() || spec?.defaultPage || '';
  if (!seed) return spec?.defaultPage ?? '';
  const aliased = aliasMapForModule(moduleId)[seed] ?? MODULE_PAGE_ALIASES[seed] ?? seed;
  if (moduleOwnsPage(moduleId, aliased)) return aliased;
  return spec?.defaultPage ?? aliased;
}

/** 擁有同一頁鍵的模組 id（可能多個，例如 monitor）。 */
export function listModuleIdsForPage(page: string | null | undefined): string[] {
  if (!page) return [];
  const aliased = aliasMap()[page] ?? page;
  const owners: string[] = [];
  for (const spec of listWorldModules()) {
    if (moduleOwnsPage(spec.id, aliased)) owners.push(spec.id);
  }
  return owners;
}

/** 切換分頁時推斷模組 id（保留當前模組命名空間、處理僅前端註冊的頁）。 */
export function inferWorldModuleIdForTab(
  tab: string | null | undefined,
  currentModuleId: string | null,
): string | null {
  if (!tab) return currentModuleId;
  if (currentModuleId && moduleOwnsPage(currentModuleId, tab)) return currentModuleId;
  return moduleIdForTab(tab, currentModuleId);
}

export function moduleIdForTab(
  tab: string | null | undefined,
  preferredModuleId?: string | null,
): string | null {
  if (!tab) return null;
  if (preferredModuleId && moduleOwnsPage(preferredModuleId, tab)) return preferredModuleId;
  const aliased = aliasMap()[tab] ?? tab;
  const owners = listModuleIdsForPage(aliased);
  if (owners.length === 1) return owners[0];
  if (owners.length > 1) {
    if (tab in MODULE_PAGE_ALIASES && owners.includes('minecraft')) return 'minecraft';
    if (aliased === 'monitor' && owners.includes('minecraft')) return 'minecraft';
    return null;
  }
  return null;
}

export function isModuleTab(tab: string | null | undefined): boolean {
  return moduleIdForTab(tab) !== null;
}

export function isModuleActivity(activity: string | null | undefined): boolean {
  return Boolean(activity && getWorldModule(activity));
}

/** 舊活動鍵正規化（歷史別名保留為空操作）。 */
export function normalizeActivityAlias(activity: string | null | undefined): string | null {
  if (!activity) return null;
  if (activity === 'linkin' || activity === 'minecraft') return null;
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
  const owners = listModuleIdsForPage(aliased);
  if (owners.length === 1) return aliased;
  if (owners.length > 1) {
    if (tab in MODULE_PAGE_ALIASES && owners.includes('minecraft')) return aliased;
    if (aliased === 'monitor' && owners.includes('minecraft')) return aliased;
    return null;
  }
  if (listWorldModules().some((spec) => hasModulePage(spec.id, aliased))) return aliased;
  return null;
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

export function hashPageForTab(tab: string, _moduleId: string): string {
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
