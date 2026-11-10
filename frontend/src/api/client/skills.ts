/**
 * EvoLoop 後端 API 客戶端 — 技能庫與 CLI Runtime（Skills）。
 *
 * 由原本的 api/client.ts 拆分而來；型別定義於 ../../types。
 */

import { apiUrl, readApiError } from './http';

// ═══════════════════════════════════════════════════════════
// 技能庫 API（Skills）
// ═══════════════════════════════════════════════════════════

export interface SkillRecord {
  id: string;
  name: string;
  content: string;
  description: string;
  trigger: string;
  enabled: boolean;
  roles: string[];
  skill_budget: number;
  created_at: string;
  updated_at: string;
  source?: string;
  skill_type?: string;
  source_path?: string;
  managed?: boolean;
  content_hash?: string;
}

export interface AgentSkillsSyncReport {
  ok: boolean;
  skills: {
    created: number;
    updated: number;
    unchanged: number;
    skipped: number;
    total_catalog: number;
  };
  mcp: {
    created: number;
    updated: number;
    unchanged: number;
  };
}

export interface SkillSaveBody {
  id?: string | null;
  name: string;
  content: string;
  description?: string;
  trigger?: string;
  enabled?: boolean;
  roles?: string[];
  skill_budget?: number;
}

export async function fetchSkills(): Promise<SkillRecord[]> {
  const resp = await fetch(apiUrl('/skills'));
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { skills: SkillRecord[] };
  return data.skills ?? [];
}

export async function saveSkill(body: SkillSaveBody): Promise<SkillRecord> {
  const resp = await fetch(apiUrl('/skills'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { skill: SkillRecord };
  return data.skill;
}

export async function toggleSkill(id: string): Promise<SkillRecord> {
  const resp = await fetch(apiUrl(`/skills/${encodeURIComponent(id)}/toggle`), { method: 'POST' });
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { skill: SkillRecord };
  return data.skill;
}

export async function deleteSkill(id: string): Promise<void> {
  const resp = await fetch(apiUrl(`/skills/${encodeURIComponent(id)}`), { method: 'DELETE' });
  if (!resp.ok) throw new Error(await readApiError(resp));
}

export async function previewSkillPrompt(role?: string): Promise<{ role: string; prompt: string }> {
  const params = role ? `?role=${encodeURIComponent(role)}` : '';
  const resp = await fetch(apiUrl(`/skills/preview${params}`));
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export interface CliRuntimeStatus {
  id: string;
  skill_id: string;
  binary: string;
  title: string;
  summary: string;
  install: string;
  group: string;
  installed: boolean;
  path: string;
  ok: boolean;
  detail: string;
}

export async function fetchCliRuntimes(): Promise<CliRuntimeStatus[]> {
  const resp = await fetch(apiUrl('/skills/cli-runtimes'));
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { runtimes: CliRuntimeStatus[] };
  return data.runtimes ?? [];
}

export interface CliHubNameGroup {
  category: string;
  count: number;
  names: string[];
}

export interface CliHubItem {
  name: string;
  display_name?: string;
  category?: string;
  description?: string;
  source?: string;
  version?: string;
  homepage?: string;
  installed?: boolean;
}

export interface CliHubView {
  ok: boolean;
  hub_installed: boolean;
  hub_path?: string;
  version?: string;
  action: string;
  items: CliHubItem[];
  categories: CliHubNameGroup[];
  total: number;
  shown: number;
  note: string;
  detail?: string;
  reason?: string;
}

export async function fetchCliHub(params: {
  action?: string;
  query?: string;
  name?: string;
  full?: boolean;
}): Promise<CliHubView> {
  const search = new URLSearchParams();
  if (params.action) search.set('action', params.action);
  if (params.query) search.set('q', params.query);
  if (params.name) search.set('name', params.name);
  if (params.full) search.set('full', '1');
  const resp = await fetch(apiUrl(`/skills/cli-hub?${search.toString()}`));
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json() as Promise<CliHubView>;
}

export async function syncAgentSkillPacks(): Promise<AgentSkillsSyncReport> {
  const resp = await fetch(apiUrl('/skills/sync-agent-packs'), { method: 'POST' });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json() as Promise<AgentSkillsSyncReport>;
}
