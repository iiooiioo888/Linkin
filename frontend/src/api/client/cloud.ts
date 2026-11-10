/**
 * EvoLoop 後端 API 客戶端 — 雲端費用、資源監控與告警規則。
 *
 * 由原本的 api/client.ts 拆分而來；型別定義於 ../../types。
 */

import type { AliyunBilling, CloudAlertsData, CloudBilling, CloudEventsData, CloudMonitoring } from '../../types';
import { apiUrl } from './http';

/** 獲取雲端費用摘要。 */
export async function fetchCloudBilling(): Promise<CloudBilling> {
  const resp = await fetch(apiUrl('/cloud/billing'));
  if (!resp.ok) throw new Error(`讀取費用失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取阿里雲 BSS 接入狀態與本月帳目。 */
export async function fetchCloudAliyun(): Promise<AliyunBilling> {
  const resp = await fetch(apiUrl('/cloud/aliyun'));
  if (!resp.ok) throw new Error(`讀取阿里雲帳目失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取資源監控歷史數據。 */
export async function fetchCloudMonitoring(range: string = '1h'): Promise<CloudMonitoring> {
  const resp = await fetch(apiUrl(`/cloud/monitoring?range=${range}`));
  if (!resp.ok) throw new Error(`讀取監控數據失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取最新資源快照。 */
export async function fetchCloudMonitoringLatest(): Promise<{ services: Record<string, { cpu: number; mem_mb: number }>; ts: string | null }> {
  const resp = await fetch(apiUrl('/cloud/monitoring/latest'));
  if (!resp.ok) throw new Error(`讀取最新快照失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取容器事件時間線。 */
export async function fetchCloudEvents(limit: number = 50): Promise<CloudEventsData> {
  const resp = await fetch(apiUrl(`/cloud/events?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取事件失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取告警規則與歷史。 */
export async function fetchCloudAlerts(): Promise<CloudAlertsData> {
  const resp = await fetch(apiUrl('/cloud/alerts'));
  if (!resp.ok) throw new Error(`讀取告警失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 創建告警規則。 */
export async function createAlertRule(rule: { name: string; metric: string; threshold: number; service: string }): Promise<Record<string, unknown>> {
  const resp = await fetch(apiUrl('/cloud/alerts'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(rule),
  });
  if (!resp.ok) throw new Error(`創建告警失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 切換告警規則啟用狀態。 */
export async function toggleAlertRule(ruleId: string): Promise<Record<string, unknown>> {
  const resp = await fetch(apiUrl(`/cloud/alerts/${encodeURIComponent(ruleId)}/toggle`), { method: 'POST' });
  if (!resp.ok) throw new Error(`切換告警失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 刪除告警規則。 */
export async function deleteAlertRule(ruleId: string): Promise<{ deleted: boolean }> {
  const resp = await fetch(apiUrl(`/cloud/alerts/${encodeURIComponent(ruleId)}`), { method: 'DELETE' });
  if (!resp.ok) throw new Error(`刪除告警失敗（HTTP ${resp.status}）`);
  return resp.json();
}
