/**
 * EvoLoop 後端 API 客戶端 — 共用 HTTP／WebSocket 基礎設施。
 *
 * 集中管理 API base URL、URL 組裝、錯誤解析等私有 helper。
 * 本檔僅供 api/client 各領域模組使用，不對外公開（index.ts 不再轉出）。
 */

import { appendGateQuery } from '../../lib/auth';
import { parseBillingHttpError } from '../../lib/billingUi';

/** 後端 API base（開發環境走 Vite 代理；生產可用 VITE_API_URL 覆寫）。 */
const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api';

/** 組出 REST API URL。 */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/** 取得 WebSocket URL（適配 Vite 代理與生產環境）。 */
export function wsUrl(path: string): string {
  const base = import.meta.env.VITE_API_URL ?? '/api';
  let url: string;
  // 生產環境或完整 URL：轉換 http(s) → ws(s)
  if (base.startsWith('http')) {
    url = base.replace(/^http/, 'ws') + path;
  } else {
    // 開發環境 Vite 代理：使用當前 host
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    url = `${proto}://${window.location.host}${base}${path}`;
  }
  return appendGateQuery(url);
}

/** 解析帳務相關的 HTTP 錯誤（402 / 403 轉贈等）。 */
export async function parseBillingError(resp: Response): Promise<string> {
  const body = await resp.json().catch(() => ({})) as { detail?: string; code?: string };
  return parseBillingHttpError(resp.status, body);
}

/** 解析一般 API 錯誤訊息（detail / error 欄位）。 */
export async function readApiError(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: string; error?: string };
    if (body.detail) return body.detail;
    if (body.error) return body.error;
  } catch {
    /* ignore */
  }
  return `請求失敗（HTTP ${resp.status}）`;
}
