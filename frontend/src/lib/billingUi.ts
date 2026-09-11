/** 靈境積分 UI 輔助（v6.0）— 純函式，可單測。 */

export const POOL_LABELS_ZH: Record<string, string> = {
  monthly_grant: '月度贈送',
  purchased: '已購買',
  contribution_unlocked: '貢獻（未鎖）',
  contribution_locked: '貢獻（鎖倉）',
  locked: '質押鎖定',
};

export function fmtCredits(n: number): string {
  if (!Number.isFinite(n)) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 10_000) return `${(n / 1000).toFixed(1)}k`;
  return n.toFixed(1);
}

export function rolloverNoticeZh(ratio: number, cap: number): string {
  const pct = Math.round(ratio * 100);
  return `月贈送積分將於每月初按 ${pct}% 滾入已購買池（上限 ${fmtCredits(cap)}），剩餘作廢`;
}

export function lockThresholdNotice(accumulated: number, threshold: number, convertible: number): string {
  return `當前累積 ${fmtCredits(accumulated)} / 閾值 ${fmtCredits(threshold)}，剩餘 ${fmtCredits(convertible)} 可轉鎖倉`;
}

export function convertPreview(amount: number, ratio = 0.4): number {
  return Math.round(amount * ratio * 10000) / 10000;
}

export function installmentProgress(paid: number, total = 3): string {
  return `已解鎖 ${paid}/${total} 期`;
}

export function earlyUnlockConfirmZh(
  forfeitedReward: number,
  penaltyPrincipal: number,
  returnedPrincipal: number,
): string {
  return (
    `提前解鎖將沒收未付獎勵 ${fmtCredits(forfeitedReward)}，` +
    `並扣除本金 5%（${fmtCredits(penaltyPrincipal)}）至故障池，` +
    `退回 ${fmtCredits(returnedPrincipal)} 至未鎖池。確認？`
  );
}

export function installmentScheduleZh(nextDue: string | undefined, intervalDays: number): string {
  if (!nextDue) return '已全部解鎖';
  const date = nextDue.slice(0, 10);
  return `下期 ${date}（每 ${intervalDays} 天一期）`;
}

export function keyFailureAppealNoticeZh(deadline: string | undefined): string {
  if (!deadline) return 'Key 故障沒收可於 30 天內申訴';
  return `Key 故障沒收申訴截止：${deadline.slice(0, 10)}`;
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
  pricing_version?: number;
  cache_savings_credits?: number;
  vendor_id?: string;
  interrupted?: boolean;
  interrupt_reason?: string;
}

export function formatChatBillingFootnote(meta: ChatBillingMeta): string {
  const parts: string[] = [];
  if (meta.credits_deducted != null) parts.push(`扣款 ${fmtCredits(meta.credits_deducted)} 積分`);
  if (meta.pricing_version != null) parts.push(`定價 v${meta.pricing_version}`);
  if (meta.cache_savings_credits != null && meta.cache_savings_credits > 0) {
    parts.push(`L3 快取節省 ${fmtCredits(meta.cache_savings_credits)}（10% 計費）`);
  }
  if (meta.vendor_id) parts.push(`廠商 ${meta.vendor_id}`);
  if (meta.interrupted && meta.interrupt_reason) parts.push(`已中斷：${meta.interrupt_reason}`);
  return parts.join(' · ');
}
