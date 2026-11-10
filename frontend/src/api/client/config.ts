/**
 * EvoLoop 後端 API 客戶端 — LLM 組態、API 路由與路由策略。
 *
 * 由原本的 api/client.ts 拆分而來；型別定義於 ../../types。
 */

import type { ApiRoutePublic, LlmOpsData, OptimizationMonitorData } from '../../types';
import { apiUrl } from './http';

// ==================== LLM 配置 ====================

export interface LlmConfig {
  configured: boolean;
  api_key: string; // 脱敏後的金鑰
  api_base: string;
  model: string;
  provider_kind?: string;
  provider_label?: string;
  lock_message?: string;
  allowed_models?: string[];
  catalog?: Array<{ id: string; name: string; owned_by: string }>;
  catalog_source?: string;
  catalog_fetched_at?: string;
  catalog_error?: string;
  route_strategy?: string;
  default_route_id?: string;
  api_routes?: ApiRoutePublic[];
  models_by_provider?: LlmOpsData['models_by_provider'];
  route_strategies?: LlmOpsData['route_strategies'];
  provider_presets?: LlmOpsData['provider_presets'];
  ops?: LlmOpsData['ops'];
}

export interface ApiRouterState {
  route_strategy: string;
  default_route_id: string;
  strategies: Array<{ id: string; label: string }>;
  presets: Array<{ id: string; name: string; api_base: string; model: string; label: string }>;
  api_routes: ApiRoutePublic[];
  allowed_models: string[];
  models_by_provider: NonNullable<LlmOpsData['models_by_provider']>;
}

/** 取得当前 LLM 配置狀態。 */
export async function fetchConfig(): Promise<LlmConfig> {
  const resp = await fetch(apiUrl('/config'));
  if (!resp.ok) throw new Error(`讀取配置失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 儲存 LLM 配置（api_key 傳空字串表示不變更可另處理）。 */
export async function saveConfig(config: {
  api_key?: string;
  api_base?: string;
  model?: string;
}): Promise<LlmConfig> {
  const resp = await fetch(apiUrl('/config'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!resp.ok) throw new Error(`儲存配置失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function fetchLlmOps(): Promise<LlmOpsData> {
  const resp = await fetch(apiUrl('/monitor/llm-ops'));
  if (!resp.ok) throw new Error(`讀取 LLM 運維失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function fetchOptimizationMonitor(): Promise<OptimizationMonitorData> {
  const resp = await fetch(apiUrl('/monitor/optimization'));
  if (!resp.ok) throw new Error(`讀取優化監控失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function refreshLlmModels(): Promise<LlmOpsData> {
  const resp = await fetch(apiUrl('/config/models/refresh'), { method: 'POST' });
  if (!resp.ok) throw new Error(`刷新模型目錄失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function updateLlmOpsPrefs(refreshIntervalSec: number): Promise<LlmOpsData> {
  const resp = await fetch(apiUrl('/config/ops'), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_interval_sec: refreshIntervalSec }),
  });
  if (!resp.ok) throw new Error(`更新運維間隔失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 以当前配置測試 LLM 連線。 */
export async function testConfig(): Promise<{ ok: boolean; reply?: string; error?: string }> {
  const resp = await fetch(apiUrl('/config/test'), { method: 'POST' });
  if (!resp.ok) throw new Error(`測試請求失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function fetchApiRoutes(): Promise<ApiRouterState> {
  const resp = await fetch(apiUrl('/config/routes'));
  if (!resp.ok) throw new Error(`讀取 API 路由失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function upsertApiRoute(payload: {
  id?: string;
  name?: string;
  provider?: string;
  api_key?: string;
  api_base?: string;
  model?: string;
  allowed_models?: string[];
  weight?: number;
  enabled?: boolean;
  fallback?: boolean;
  is_default?: boolean;
  models_locked?: boolean;
  keep_api_key?: boolean;
  provider_routing?: Record<string, unknown> | null;
}): Promise<ApiRouterState> {
  const resp = await fetch(apiUrl('/config/routes'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`儲存 API 路由失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function deleteApiRoute(routeId: string): Promise<ApiRouterState> {
  const resp = await fetch(apiUrl(`/config/routes/${encodeURIComponent(routeId)}`), { method: 'DELETE' });
  if (!resp.ok) throw new Error(`刪除 API 路由失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function refreshApiRoute(routeId: string): Promise<ApiRoutePublic> {
  const resp = await fetch(apiUrl(`/config/routes/${encodeURIComponent(routeId)}/refresh`), { method: 'POST' });
  if (!resp.ok) throw new Error(`刷新路由目錄失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function testApiRoute(routeId: string): Promise<{ ok: boolean; reply?: string; error?: string; route_id?: string }> {
  const resp = await fetch(apiUrl(`/config/routes/${encodeURIComponent(routeId)}/test`), { method: 'POST' });
  if (!resp.ok) throw new Error(`測試路由失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function updateRouteStrategy(routeStrategy: string, defaultRouteId?: string): Promise<ApiRouterState> {
  const resp = await fetch(apiUrl('/config/strategy'), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ route_strategy: routeStrategy, default_route_id: defaultRouteId }),
  });
  if (!resp.ok) throw new Error(`更新路由策略失敗（HTTP ${resp.status}）`);
  return resp.json();
}
