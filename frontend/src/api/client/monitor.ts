/**
 * EvoLoop 後端 API 客戶端 — 監控中心（Dashboard / OPC / Hub / Agent）與記憶庫。
 *
 * 由原本的 api/client.ts 拆分而來；型別定義於 ../../types。
 */

import type { AgentMonitorData, AgentMonitorPrefs, DashboardData, HubMonitorData, OpcMonitorData, RoleAgent } from '../../types';
import { apiUrl } from './http';

/** 一次性拉取監控彙總快照（REST 降級）。 */
export async function fetchMonitorHubSnapshot(): Promise<Record<string, unknown>> {
  const resp = await fetch(apiUrl('/monitor/hub-snapshot'));
  if (!resp.ok) throw new Error(`監控快照失敗（HTTP ${resp.status}）`);
  return resp.json();
}

// ==================== 記憶庫管理 ====================

/** 記憶項目 */
export interface MemoryItem {
  id: string;
  text: string;
  metadata: Record<string, unknown>;
}

/** 列出記憶庫中的記憶（分頁）。 */
export async function fetchMemories(limit: number = 100, offset: number = 0): Promise<{
  total: number;
  offset: number;
  limit: number;
  memories: MemoryItem[];
  error?: string;
}> {
  const resp = await fetch(apiUrl(`/memories?limit=${limit}&offset=${offset}`));
  if (!resp.ok) throw new Error(`讀取記憶庫失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 刪除單條記憶。 */
export async function deleteMemory(memoryId: string): Promise<{ deleted: boolean; id: string }> {
  const resp = await fetch(apiUrl(`/memories/${encodeURIComponent(memoryId)}`), {
    method: 'DELETE',
  });
  if (!resp.ok) throw new Error(`刪除記憶失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 清理過期或低品質記憶。 */
export async function cleanupMemories(
  maxAgeDays: number = 30,
  minScore?: number,
): Promise<{ deleted_count: number }> {
  const params = new URLSearchParams({ max_age_days: String(maxAgeDays) });
  if (minScore != null) params.set('min_score', String(minScore));
  const resp = await fetch(apiUrl(`/memories/cleanup?${params.toString()}`), {
    method: 'POST',
  });
  if (!resp.ok) throw new Error(`清理記憶失敗（HTTP ${resp.status}）`);
  return resp.json();
}

// ==================== 控制面版 ====================

/** 取得控制面版聚合資料（統計/任務/存檔/審計/能力）。 */
export async function fetchDashboard(): Promise<DashboardData> {
  const resp = await fetch(apiUrl('/dashboard'));
  if (!resp.ok) throw new Error(`讀取控制面版失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 監控中心 OPC 快照（護欄 / 審計 / 即時標籤）。 */
export async function fetchOpcMonitor(): Promise<OpcMonitorData> {
  const resp = await fetch(apiUrl('/monitor/opc'));
  if (!resp.ok) throw new Error(`讀取 OPC 監控失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 監控中心 AI Hub 快照（探針 / 熔斷 / 呼叫日誌 / 預算）。 */
export async function fetchHubMonitor(): Promise<HubMonitorData> {
  const resp = await fetch(apiUrl('/monitor/hub'));
  if (!resp.ok) throw new Error(`讀取 Hub 監控失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 監控中心角色 Agent（每位公司角色獨立任務列表）。 */
export async function fetchAgentMonitor(): Promise<AgentMonitorData> {
  const resp = await fetch(apiUrl('/monitor/agents'));
  if (!resp.ok) throw new Error(`讀取角色 Agent 監控失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function updateAgentSettings(roleId: string, body: Record<string, unknown>): Promise<RoleAgent> {
  const resp = await fetch(apiUrl(`/monitor/agents/${encodeURIComponent(roleId)}/settings`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(detail || `更新角色設定失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function resetAgentSettings(roleId: string): Promise<RoleAgent> {
  const resp = await fetch(apiUrl(`/monitor/agents/${encodeURIComponent(roleId)}/reset`), { method: 'POST' });
  if (!resp.ok) throw new Error(`還原角色設定失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function createCustomAgent(body: Record<string, unknown>): Promise<RoleAgent> {
  const resp = await fetch(apiUrl('/monitor/agents'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(detail || `建立角色失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function deleteCustomAgent(roleId: string): Promise<void> {
  const resp = await fetch(apiUrl(`/monitor/agents/${encodeURIComponent(roleId)}`), { method: 'DELETE' });
  if (!resp.ok) throw new Error(`刪除角色失敗（HTTP ${resp.status}）`);
}

export async function updateAgentMonitorPrefs(body: Partial<AgentMonitorPrefs>): Promise<AgentMonitorPrefs> {
  const resp = await fetch(apiUrl('/monitor/agents/prefs'), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`更新監控偏好失敗（HTTP ${resp.status}）`);
  return resp.json();
}
