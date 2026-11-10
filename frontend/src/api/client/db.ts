/**
 * EvoLoop 後端 API 客戶端 — 數據庫連接池管理。
 *
 * 由原本的 api/client.ts 拆分而來；型別定義於 ../../types。
 */

import { apiUrl } from './http';

// ==================== 數據庫連接池管理 ====================

export interface DbConnectionInfo {
  id: string;
  db_path: string;
  created_at: string;
  last_used_at: string;
  is_active: boolean;
  query_count: number;
  avg_latency_ms: number;
}

export interface DbPoolStats {
  pool_size: number;
  active_connections: number;
  idle_connections: number;
  total_queries: number;
  avg_query_latency_ms: number;
  connections: DbConnectionInfo[];
}

/** 獲取數據庫連接池統計信息 */
export async function fetchDbPoolStats(): Promise<DbPoolStats> {
  const resp = await fetch(apiUrl('/admin/db/pool/stats'));
  if (!resp.ok) throw new Error(`讀取連接池狀態失敗（HTTP ${resp.status}`);
  return resp.json();
}

/** 刷新連接池（關閉空閒連接） */
export async function refreshDbPool(min_idle: number = 2): Promise<DbPoolStats> {
  const resp = await fetch(apiUrl('/admin/db/pool/refresh'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ min_idle }),
  });
  if (!resp.ok) throw new Error(`刷新連接池失敗（HTTP ${resp.status}`);
  return resp.json();
}

/** 關閉指定連接 */
export async function closeDbConnection(connection_id: string): Promise<{ success: boolean }> {
  const resp = await fetch(apiUrl(`/admin/db/pool/connection/${encodeURIComponent(connection_id)}`), {
    method: 'DELETE',
  });
  if (!resp.ok) throw new Error(`關閉連接失敗（HTTP ${resp.status}`);
  return resp.json();
}

/** 執行健康檢查 */
export async function runDbHealthCheck(): Promise<{ healthy: boolean; details: string }> {
  const resp = await fetch(apiUrl('/admin/db/health'), {
    method: 'POST',
  });
  if (!resp.ok) throw new Error(`健康檢查失敗（HTTP ${resp.status}`);
  return resp.json();
}
