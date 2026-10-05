/** 對話調用資訊 UI 輔助（僅 Token／模型等，無金額）。 */

export function fmtCredits(n: number): string {
  if (!Number.isFinite(n)) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 10_000) return `${(n / 1000).toFixed(1)}k`;
  return n.toFixed(1);
}

export function parseBillingHttpError(status: number, body: { detail?: string; code?: string }): string {
  if (status === 402) {
    return body.detail || '已達調用上限，請稍後再試或聯絡管理員';
  }
  if (status === 403 && body.detail?.includes('轉贈')) {
    return body.detail || '此操作目前無法完成';
  }
  return body.detail || `請求失敗（HTTP ${status}）`;
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

/** 對話 footnote：僅 Token／模型等調用資訊。 */
export function formatChatBillingFootnote(meta: ChatBillingMeta): string {
  const parts: string[] = [];
  const inp = meta.input_tokens ?? 0;
  const out = meta.output_tokens ?? 0;
  if (inp > 0 || out > 0) parts.push(`Token ${inp}/${out}`);
  if (meta.models?.length) parts.push(meta.models.join(', '));
  if (meta.pricing_version != null) parts.push(`定價 v${meta.pricing_version}`);
  if (meta.cache_read_tokens || meta.cache_write_tokens) {
    parts.push(`快取 Token 讀 ${meta.cache_read_tokens ?? 0} · 寫 ${meta.cache_write_tokens ?? 0}`);
  }
  if (meta.vendor_id) parts.push(`廠商 ${meta.vendor_id}`);
  if (meta.interrupted && meta.interrupt_reason) parts.push(`已中斷：${meta.interrupt_reason}`);
  return parts.join(' · ');
}

/** 對話結束後刷新帳務快照（內部用，無 UI）。 */
export function requestBillingRefresh(): void {
  window.dispatchEvent(new CustomEvent('linkin:billing-refresh'));
}
