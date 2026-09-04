/**
 * 靈境·Linkin API（VITE_API_URL + fetch，開發時經 /api 代理）。
 */
const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api';

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(apiUrl(path), {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  const text = await resp.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!resp.ok) {
    const detail = (data as { detail?: unknown })?.detail;
    const message =
      typeof detail === 'string'
        ? detail
        : detail && typeof detail === 'object' && 'message' in detail
          ? String((detail as { message: string }).message)
          : `請求失敗（HTTP ${resp.status}）`;
    throw new Error(message);
  }
  return data as T;
}

export type Constitution = {
  world_name: string;
  world_name_zh_hant?: string;
  tagline?: string;
  foundation?: Record<string, unknown>;
  factions?: Array<Record<string, unknown>>;
  magic?: Record<string, unknown>;
  regions?: Array<Record<string, unknown>>;
  content_boundaries?: string[];
  consistency_rules?: string[];
  item_balance?: Record<string, unknown>;
};

export type NpcCard = {
  id?: string;
  name: string;
  faction: string;
  occupation: string;
  personality: string;
  backstory: string;
  location: string;
  speech_style: string;
  relationships?: Record<string, string>;
  backend?: string;
};

export type Quest = {
  id: string;
  title: string;
  quest_type: string;
  difficulty: string;
  region?: string;
  description?: string;
};

export type Building = {
  id: string;
  prompt: string;
  style: string;
  location: unknown;
  region?: string;
  block_count: number;
  status?: string;
  note?: string;
  kind?: string;
  width?: number;
  height?: number;
  length?: number;
  voxel_count?: number;
  schematic_version?: number;
  format?: string;
  biome?: string;
};

export type BuildingPreview = {
  id: string;
  kind?: string;
  width: number;
  height: number;
  length: number;
  version: number;
  data_version?: number;
  voxel_count: number;
  biome?: string;
  palette: Array<{ name: string; color: string; opacity?: number; emissive?: string }>;
  voxels: Array<{ x: number; y: number; z: number; i: number }>;
  schematic_base64?: string;
  schematic_filename?: string;
  building?: Partial<Building>;
};

export type Item = {
  id: string;
  name: string;
  type: string;
  rarity: string;
  attributes: Record<string, unknown>;
  description?: string;
};

export type WorldEvent = {
  id: string;
  text: string;
  kind?: string;
  title?: string;
  updated_at?: string;
};

export type Overview = {
  world_name: string;
  will?: string;
  npc_count: number;
  quest_count: number;
  event_count: number;
  item_count: number;
  building_count: number;
  player_records?: number;
  factions: string[];
  magic?: string;
  compliance: {
    constitution_loaded: boolean;
    factions_defined: boolean;
    magic_defined: boolean;
    rag: { chroma: boolean; fallback?: string | null; error?: string | null };
    minecraft?: {
      dry_run?: boolean;
      enabled?: boolean;
      connected?: boolean;
    };
  };
  minecraft?: MinecraftStatus;
};

export type MinecraftAudit = {
  ts?: string;
  tool?: string;
  remote?: string;
  ok?: boolean;
  dry_run?: boolean;
  error?: string;
  duration_ms?: number;
};

export type MinecraftStatus = {
  enabled: boolean;
  live: boolean;
  dry_run: boolean;
  url: string;
  world: string;
  token_configured: boolean;
  connected?: boolean;
  max_blocks?: number;
  company_tools?: string[];
  tools?: string[];
  recent?: MinecraftAudit[];
  probe?: {
    ok?: boolean;
    connected?: boolean;
    dry_run?: boolean;
    message?: string;
    error?: string;
    remote_tools?: string[];
  };
};

export const fetchConstitution = () => request<Constitution>('/linkin/constitution');
export const saveConstitution = (body: Record<string, unknown>) =>
  request<Constitution>('/linkin/constitution', { method: 'PUT', body: JSON.stringify(body) });

export const fetchNpcs = () => request<{ npcs: NpcCard[]; count: number }>('/linkin/npcs');
export const createNpc = (body: NpcCard) =>
  request<{ npc: NpcCard }>('/linkin/npcs', { method: 'POST', body: JSON.stringify(body) });
export const updateNpc = (id: string, body: Partial<NpcCard>) =>
  request<{ npc: NpcCard }>(`/linkin/npcs/${id}`, { method: 'PUT', body: JSON.stringify(body) });
export const deleteNpc = (id: string) =>
  request<{ deleted: boolean }>(`/linkin/npcs/${id}`, { method: 'DELETE' });
export const npcDialogue = (id: string, playerMessage: string) =>
  request<{ reply: string; rag: { hits: unknown[]; backend: unknown } }>(
    `/linkin/npcs/${id}/dialogue`,
    { method: 'POST', body: JSON.stringify({ playerMessage }) },
  );

export const generateQuest = (body: { playerId: string; questType: string; difficulty: string; region?: string }) =>
  request<{ quest: Quest }>('/linkin/quests/generate', { method: 'POST', body: JSON.stringify(body) });
export const fetchQuests = () => request<{ quests: Quest[]; count: number }>('/linkin/quests');
export const deleteQuest = (id: string) =>
  request<{ deleted: boolean }>(`/linkin/quests/${id}`, { method: 'DELETE' });

export const generateBuilding = (body: {
  prompt: string;
  style: string;
  location: string;
  region: string;
  block_count: number;
}) => request<{ building: Building; preview?: BuildingPreview | null }>('/linkin/buildings/generate', { method: 'POST', body: JSON.stringify(body) });
export const fetchBuildings = () => request<{ buildings: Building[]; count: number }>('/linkin/buildings');
export const fetchBuildingPreview = (id: string) => request<BuildingPreview>(`/linkin/buildings/${id}/preview`);
export const schematicUrl = (id: string) => apiUrl(`/linkin/buildings/${id}/schematic`);
export const deleteBuilding = (id: string) =>
  request<{ deleted: boolean }>(`/linkin/buildings/${id}`, { method: 'DELETE' });

export const importSchematicBase64 = (
  schematicBase64: string,
  meta: { prompt?: string; style?: string; location?: string; region?: string },
) =>
  request<{ building: Building; preview: BuildingPreview }>('/linkin/buildings/import-base64', {
    method: 'POST',
    body: JSON.stringify({
      schematic_base64: schematicBase64,
      prompt: meta.prompt ?? '',
      style: meta.style ?? '',
      location: meta.location ?? '',
      region: meta.region ?? '',
    }),
  });

export async function importSchematic(
  file: File,
  meta: { prompt?: string; style?: string; location?: string; region?: string },
): Promise<{ building: Building; preview: BuildingPreview }> {
  const form = new FormData();
  form.append('file', file);
  if (meta.prompt) form.append('prompt', meta.prompt);
  if (meta.style) form.append('style', meta.style);
  if (meta.location) form.append('location', meta.location);
  if (meta.region) form.append('region', meta.region);
  const resp = await fetch(apiUrl('/linkin/buildings/import'), { method: 'POST', body: form });
  const text = await resp.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!resp.ok) {
    const detail = (data as { detail?: unknown })?.detail;
    const message =
      typeof detail === 'string'
        ? detail
        : detail && typeof detail === 'object' && 'message' in detail
          ? String((detail as { message: string }).message)
          : `請求失敗（HTTP ${resp.status}）`;
    throw new Error(message);
  }
  return data as { building: Building; preview: BuildingPreview };
}

export const fetchItems = () => request<{ items: Item[]; count: number }>('/linkin/items');
export const createItem = (body: Omit<Item, 'id'>) =>
  request<{ item: Item }>('/linkin/items', { method: 'POST', body: JSON.stringify(body) });
export const deleteItem = (id: string) =>
  request<{ deleted: boolean }>(`/linkin/items/${id}`, { method: 'DELETE' });

export const fetchEvents = () => request<{ events: WorldEvent[]; count: number }>('/linkin/events');

export const fetchOverview = () => request<Overview>('/linkin/overview');

export const fetchMinecraftStatus = () => request<MinecraftStatus>('/linkin/minecraft/status');
export const probeMinecraft = () =>
  request<MinecraftStatus['probe']>('/linkin/minecraft/probe', { method: 'POST', body: '{}' });
export const callMinecraftTool = (tool: string, arguments_: Record<string, unknown>) =>
  request<Record<string, unknown>>('/linkin/minecraft/call', {
    method: 'POST',
    body: JSON.stringify({ tool, arguments: arguments_ }),
  });
export const dispatchBuilding = (id: string) =>
  request<{ building: Building; minecraft: Record<string, unknown> }>(
    `/linkin/buildings/${id}/dispatch`,
    { method: 'POST', body: '{}' },
  );
