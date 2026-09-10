import type { ComponentType } from 'react';
import type { ModulePageProps } from './types';

export type ModulePageLoader = () => Promise<{ default: ComponentType<ModulePageProps> }>;

const loaders = new Map<string, ModulePageLoader>();

function pageKey(moduleId: string, page: string): string {
  return `${moduleId}:${page}`;
}

export function registerModulePage(moduleId: string, page: string, loader: ModulePageLoader): void {
  loaders.set(pageKey(moduleId, page), loader);
}

export function registerModulePages(moduleId: string, pages: Record<string, ModulePageLoader>): void {
  for (const [page, loader] of Object.entries(pages)) {
    registerModulePage(moduleId, page, loader);
  }
}

export function getModulePageLoader(moduleId: string, page: string): ModulePageLoader | null {
  return loaders.get(pageKey(moduleId, page)) ?? loaders.get(pageKey(moduleId, '*')) ?? null;
}

export function hasModulePage(moduleId: string, page: string): boolean {
  return getModulePageLoader(moduleId, page) !== null;
}
