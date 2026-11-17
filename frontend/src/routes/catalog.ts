/**
 * 使用者看得見的四個入口。掛載檔缺席時仍保留入口，頁面顯示「尚未接上」。
 */
import type { ComponentType } from 'react';

export const SURFACE_ORDER = [
  'chat',
  'context-compression',
  'prompt-compression',
  'history',
] as const;

export type SurfaceId = (typeof SURFACE_ORDER)[number];

export const SURFACE_LABEL: Record<SurfaceId, string> = {
  chat: '對話',
  'context-compression': '上下文壓縮',
  'prompt-compression': '提示詞壓縮',
  history: '歷史對話記錄',
};

export type SurfaceMountModule = {
  id: string;
  label?: string;
  Page?: ComponentType;
};

export type SurfaceEntry = {
  id: SurfaceId;
  label: string;
  ready: boolean;
  Page: ComponentType | null;
};

export function isSurfaceId(value: string): value is SurfaceId {
  return (SURFACE_ORDER as readonly string[]).includes(value);
}

export function surfaceFromHash(hash: string): SurfaceId {
  const raw = hash.replace(/^#\/?/, '').split(/[/?#]/)[0] ?? '';
  let id = raw;
  try {
    id = decodeURIComponent(raw);
  } catch {
    id = raw;
  }
  return isSurfaceId(id) ? id : 'chat';
}

export function hashForSurface(id: SurfaceId): string {
  return `#/${id}`;
}

/** 依固定順序收成四個入口。未知 id 不進導覽。 */
export function listSurfaces(
  modules: Record<string, Partial<SurfaceMountModule>>,
): SurfaceEntry[] {
  const byId = new Map<SurfaceId, SurfaceMountModule>();
  for (const mod of Object.values(modules)) {
    if (!mod?.id || !isSurfaceId(mod.id) || typeof mod.Page !== 'function') continue;
    byId.set(mod.id, {
      id: mod.id,
      label: mod.label,
      Page: mod.Page,
    });
  }
  return SURFACE_ORDER.map((id) => {
    const found = byId.get(id);
    if (!found?.Page) {
      return { id, label: SURFACE_LABEL[id], ready: false, Page: null };
    }
    return {
      id,
      label: found.label?.trim() || SURFACE_LABEL[id],
      ready: true,
      Page: found.Page,
    };
  });
}
