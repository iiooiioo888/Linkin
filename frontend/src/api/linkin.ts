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
};

export type Item = {
  id: string;
  name: string;
  type: string;
  rarity: string;
  attributes: Record<string, unknown>;
  description?: string;
};

export type Overview = {
  world_name: string;
  will?: string;
  npc_count: number;
  quest_count: number;
  event_count: number;
  item_count: number;
  building_count: number;
  factions: string[];
  magic?: string;
  compliance: {
    constitution_loaded: boolean;
    factions_defined: boolean;
    magic_defined: boolean;
    rag: { chroma: boolean; fallback?: string | null; error?: string | null };
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

export const generateBuilding = (body: {
  prompt: string;
  style: string;
  location: string;
  region: string;
  block_count: number;
}) => request<{ building: Building }>('/linkin/buildings/generate', { method: 'POST', body: JSON.stringify(body) });

export const fetchItems = () => request<{ items: Item[]; count: number }>('/linkin/items');
export const createItem = (body: Omit<Item, 'id'>) =>
  request<{ item: Item }>('/linkin/items', { method: 'POST', body: JSON.stringify(body) });

export const fetchOverview = () => request<Overview>('/linkin/overview');
