/**
 * EvoLoop 後端 API 客戶端 — 調用用量帳務（Billing / Wallet / Contributor / Admin）。
 *
 * 由原本的 api/client.ts 拆分而來；型別定義於 ../../types。
 */

import type { BillingLedgerEntry, BillingSnapshot, BillingUsageEvent } from '../../types';
import { apiUrl } from './http';

// ═══════════════════════════════════════════════════════════
// 雲控制台 API
// ═══════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════
// 調用用量帳務 API（/billing）
// ═══════════════════════════════════════════════════════════

export async function fetchBilling(): Promise<BillingSnapshot> {
  const resp = await fetch(apiUrl('/billing'));
  if (!resp.ok) throw new Error(`讀取帳務失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export interface BillingOverview {
  user_id: string;
  period_key: string;
  monthly_used_credits: number;
  balance_credits: number;
  low_balance: boolean;
  unhealthy_keys_count: number;
  unhealthy_keys: Array<{ key_id?: string; status?: string; health_score?: number }>;
}

export async function fetchBillingOverview(): Promise<BillingOverview> {
  const resp = await fetch(apiUrl('/billing/overview'));
  if (!resp.ok) throw new Error(`讀取帳務總覽失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** Token 用量看板 HTML（Linkin 計費庫請求級 usage） */
export function tokenDashboardUrl(days = 90): string {
  const d = Math.max(1, Math.min(365, Math.floor(days)));
  return apiUrl(`/billing/token-dashboard?days=${d}`);
}

export function openTokenDashboard(days = 90): void {
  window.open(tokenDashboardUrl(days), '_blank', 'noopener,noreferrer');
}

export async function fetchBillingLedger(limit = 50): Promise<{ user_id: string; entries: BillingLedgerEntry[] }> {
  const resp = await fetch(apiUrl(`/billing/ledger?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取分類帳失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function fetchBillingUsage(limit = 50): Promise<{ user_id: string; events: BillingUsageEvent[] }> {
  const resp = await fetch(apiUrl(`/billing/usage?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取用量失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function topupBillingCredits(credits: number, note = ''): Promise<unknown> {
  const resp = await fetch(apiUrl('/billing/topup'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credits, note }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `操作失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function assignBillingPlan(planId: string): Promise<unknown> {
  const resp = await fetch(apiUrl('/billing/assign-plan'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_id: planId }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `方案切換失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function fetchBillingGrants(limit = 50) {
  const resp = await fetch(apiUrl(`/billing/grants?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取入帳來源失敗（HTTP ${resp.status}）`);
  return resp.json() as Promise<{ items: import('../../types').BillingGrant[] }>;
}

export async function fetchBillingRollover(limit = 20) {
  const resp = await fetch(apiUrl(`/billing/rollover-records?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取滾存紀錄失敗（HTTP ${resp.status}）`);
  return resp.json() as Promise<{ items: Record<string, unknown>[] }>;
}

export async function fetchBillingPoolLedger(limit = 50) {
  const resp = await fetch(apiUrl(`/billing/pools/ledger?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取池帳本失敗（HTTP ${resp.status}）`);
  return resp.json() as Promise<{ items: import('../../types').PoolLedgerEntry[] }>;
}

export async function fetchBillingAppeals(limit = 20) {
  const resp = await fetch(apiUrl(`/billing/appeals?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取申訴失敗（HTTP ${resp.status}）`);
  return resp.json() as Promise<{ appeals: import('../../types').BillingAppeal[] }>;
}

export async function submitBillingAppeal(
  reason: string,
  detail: string,
  taskId = '',
  opts: { appealKind?: string; installmentId?: string } = {},
) {
  const resp = await fetch(apiUrl('/billing/appeals'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      reason,
      detail,
      task_id: taskId,
      appeal_kind: opts.appealKind ?? 'general',
      installment_id: opts.installmentId ?? '',
    }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `申訴失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function convertContribution(amount: number) {
  const resp = await fetch(apiUrl(`/billing/contribution/convert?amount=${amount}`), { method: 'POST' });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `轉換失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function lockContribution(amount: number, lockDays: number) {
  const resp = await fetch(apiUrl('/billing/contributor/contribution/lock'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ amount, lock_days: lockDays }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `鎖倉失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function fetchContributorStatus() {
  const resp = await fetch(apiUrl('/billing/contributor/contribution/status'));
  if (!resp.ok) throw new Error(`讀取貢獻狀態失敗（HTTP ${resp.status}）`);
  return resp.json() as Promise<import('../../types').ContributionStatus>;
}

export async function fetchContributorEarnings() {
  const resp = await fetch(apiUrl('/billing/contributor/earnings'));
  if (!resp.ok) throw new Error(`讀取貢獻收益失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function bindContributorKey(
  encryptedKey: string,
  opts: {
    vendorId?: string;
    models?: string[];
    dailyTokenCap?: number;
    concurrency?: number;
    minPrice?: number;
    activeHours?: number[];
    tosClass?: string;
    orgId?: string;
    label?: string;
    apiBase?: string;
  } = {},
) {
  const resp = await fetch(apiUrl('/billing/contributor/bind-key'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      encrypted_key: encryptedKey,
      vendor_id: opts.vendorId ?? 'self_host',
      models: opts.models ?? [],
      daily_token_cap: opts.dailyTokenCap ?? 0,
      concurrency: opts.concurrency ?? 1,
      min_price: opts.minPrice ?? 0,
      active_hours: opts.activeHours ?? [0, 23],
      tos_class: opts.tosClass ?? 'self_host',
      org_id: opts.orgId ?? '',
      label: opts.label ?? '',
      api_base: opts.apiBase ?? '',
    }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `綁定失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function fetchContributorKeys() {
  const resp = await fetch(apiUrl('/billing/contributor/keys'));
  if (!resp.ok) throw new Error(`讀取 Key 列表失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function fetchContributorKeyHealth(keyId: string) {
  const resp = await fetch(apiUrl(`/billing/contributor/keys/${encodeURIComponent(keyId)}/health`));
  if (!resp.ok) throw new Error(`讀取 Key 健康度失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function triggerInstallments(force = false) {
  const resp = await fetch(
    apiUrl(`/billing/contributor/contribution/unlock-installments?force=${force ? 'true' : 'false'}`),
    { method: 'POST' },
  );
  if (!resp.ok) throw new Error(`分期處理失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function earlyUnlockContribution(installmentId: string) {
  const resp = await fetch(apiUrl('/billing/contributor/contribution/early-unlock'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ installment_id: installmentId }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `提前解鎖失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

type AdminHeaders = Record<string, string>;

function adminFetch(path: string, init: RequestInit = {}, headers: AdminHeaders = {}) {
  return fetch(apiUrl(path), {
    ...init,
    headers: { ...headers, ...(init.headers as Record<string, string>) },
  });
}

export async function adminListPricingConfigs(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/pricing-configs', {}, h);
  if (!resp.ok) throw new Error('讀取定價列表失敗');
  return resp.json();
}

export async function adminActivatePricing(version: number, h: AdminHeaders) {
  const resp = await adminFetch(`/admin/billing/pricing-configs/${version}/activate`, { method: 'POST' }, h);
  if (!resp.ok) throw new Error('啟用定價失敗');
  return resp.json();
}

export async function adminListCreditPolicies(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/credit-policies', {}, h);
  if (!resp.ok) throw new Error('讀取政策列表失敗');
  return resp.json();
}

export async function adminActivateCreditPolicy(version: number, h: AdminHeaders) {
  const resp = await adminFetch(`/admin/billing/credit-policies/${version}/activate`, { method: 'POST' }, h);
  if (!resp.ok) throw new Error('啟用政策失敗');
  return resp.json();
}

export async function adminListVendorConfigs(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/vendor-configs', {}, h);
  if (!resp.ok) throw new Error('讀取廠商配置失敗');
  return resp.json();
}

export async function adminActivateVendor(version: number, h: AdminHeaders) {
  const resp = await adminFetch(`/admin/billing/vendor-configs/${version}/activate`, { method: 'POST' }, h);
  if (!resp.ok) throw new Error('啟用廠商配置失敗');
  return resp.json();
}

export async function adminListAppeals(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/appeals', {}, h);
  if (!resp.ok) throw new Error('讀取申訴列表失敗');
  return resp.json();
}

export async function adminResolveAppeal(appealId: string, h: AdminHeaders) {
  const resp = await adminFetch(`/admin/billing/appeals/${appealId}/resolve`, { method: 'POST' }, h);
  if (!resp.ok) throw new Error('處理申訴失敗');
  return resp.json();
}

export async function adminRunRollover(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/rollover/run', { method: 'POST' }, h);
  if (!resp.ok) throw new Error('執行滾存失敗');
  return resp.json();
}

export async function adminListRollover(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/rollover-records', {}, h);
  if (!resp.ok) throw new Error('讀取滾存失敗');
  return resp.json();
}

export async function adminGetFaultPool(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/fault-pool', {}, h);
  if (!resp.ok) throw new Error('讀取 fault pool 失敗');
  return resp.json();
}

export async function adminGetRoutingStats(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/routing/stats', {}, h);
  if (!resp.ok) throw new Error('讀取路由統計失敗');
  return resp.json();
}

export async function adminResumePublicPool(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/fault-pool/resume-public', { method: 'POST' }, h);
  if (!resp.ok) throw new Error('恢復公共池失敗');
  return resp.json();
}

export async function adminSeedContribution(accountId: string, amount: number, note = '', h: AdminHeaders = {}) {
  const resp = await adminFetch(
    '/admin/billing/contribution/seed',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id: accountId, amount, note }),
    },
    h,
  );
  if (!resp.ok) throw new Error('注入貢獻資料失敗');
  return resp.json();
}

export async function adminGetCacheStats(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/cache-stats', {}, h);
  if (!resp.ok) throw new Error('讀取快取統計失敗');
  return resp.json();
}

export async function adminGetTaskLedger(taskId: string, h: AdminHeaders) {
  const resp = await adminFetch(`/admin/billing/task-ledger/${taskId}`, {}, h);
  if (!resp.ok) throw new Error('讀取任務分類帳失敗');
  return resp.json();
}

/** @deprecated 使用 fetchBilling */
export const fetchWallet = fetchBilling;
export const fetchWalletLedger = fetchBillingLedger;
export const topupWallet = (amountUsd: number, note = '') => topupBillingCredits(amountUsd * 1000, note);
