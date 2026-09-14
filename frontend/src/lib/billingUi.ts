/** 靈境積分 UI 輔助 — 對話扣款與餘額顯示（計費中心已移除）。 */

export function fmtCredits(n: number): string {
  if (!Number.isFinite(n)) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 10_000) return `${(n / 1000).toFixed(1)}k`;
  return n.toFixed(1);
}

export function parseBillingHttpError(status: number, body: { detail?: string; code?: string }): string {
  if (status === 402) {
    return body.detail || '靈境積分不足，請充值或升級方案後再試';
  }
  if (status === 403 && body.detail?.includes('轉贈')) {
    return '積分不可轉贈、轉移或提現';
  }
  return body.detail || `帳務錯誤（HTTP ${status}）`;
}

export interface ChatBillingMeta {
  credits_deducted?: number;
  input_tokens?: number;
  output_tokens?: number;
  cache_read_tokens?: number;
  cache_write_tokens?: number;
  call_count?: number;
  models?: string[];
  pricing_version?: number;
  cache_savings_credits?: number;
  vendor_id?: string;
  session_id?: string;
  interrupted?: boolean;
  interrupt_reason?: string;
}

export function formatChatBillingFootnote(meta: ChatBillingMeta): string {
  const parts: string[] = [];
  if (meta.credits_deducted != null) parts.push(`扣款 ${fmtCredits(meta.credits_deducted)} 積分`);
  const inp = meta.input_tokens ?? 0;
  const out = meta.output_tokens ?? 0;
  if (inp > 0 || out > 0) parts.push(`Token ${inp}/${out}`);
  if (meta.models?.length) parts.push(meta.models.join(', '));
  if (meta.pricing_version != null) parts.push(`定價 v${meta.pricing_version}`);
  if (meta.cache_savings_credits != null && meta.cache_savings_credits > 0) {
    parts.push(`L3 快取節省 ${fmtCredits(meta.cache_savings_credits)}（10% 計費）`);
  }
  if (meta.vendor_id) parts.push(`廠商 ${meta.vendor_id}`);
  if (meta.interrupted && meta.interrupt_reason) parts.push(`已中斷：${meta.interrupt_reason}`);
  return parts.join(' · ');
}

/** 觸發全域錢包刷新（對話扣款後立即更新餘額） */
export function requestWalletRefresh(): void {
  window.dispatchEvent(new CustomEvent('linkin:wallet-refresh'));
}
