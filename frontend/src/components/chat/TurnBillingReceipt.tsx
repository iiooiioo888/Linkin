/**
 * 單輪對話扣款／Token 用量摘要（assistant 訊息下方）。
 */
import { useTranslation } from 'react-i18next';
import type { ChatBillingMeta } from '../../lib/billingUi';
import { fmtCredits } from '../../lib/billingUi';

interface TurnBillingReceiptProps {
  billing: ChatBillingMeta;
}

export default function TurnBillingReceipt({ billing }: TurnBillingReceiptProps) {
  const { t } = useTranslation();
  const credits = billing.credits_deducted ?? 0;
  const hasTokens = (billing.input_tokens ?? 0) > 0 || (billing.output_tokens ?? 0) > 0;
  if (credits <= 0 && !hasTokens) return null;

  const models = billing.models ?? [];
  const cacheRead = billing.cache_read_tokens ?? 0;
  const cacheWrite = billing.cache_write_tokens ?? 0;

  return (
    <div
      className="mt-2 rounded-lg border border-[color-mix(in_srgb,var(--console-blue)_25%,transparent)] bg-[color-mix(in_srgb,var(--console-blue)_6%,transparent)] px-3 py-2 text-[11px]"
      data-testid="turn-billing-receipt"
    >
      <div className="mb-1.5 font-medium text-[var(--console-blue)]">{t('billing.turnReceipt')}</div>
      <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[var(--console-sub)]">
        <span>{t('billing.creditsCharged')}</span>
        <span className="tabular-nums font-medium text-[var(--console-ink)]">
          −{fmtCredits(credits)} <span className="text-[var(--console-faint)]">cr</span>
        </span>
        {hasTokens ? (
          <>
            <span>{t('billing.tokensInOut')}</span>
            <span className="tabular-nums text-[var(--console-ink)]">
              {billing.input_tokens ?? 0} / {billing.output_tokens ?? 0}
            </span>
          </>
        ) : null}
        {cacheRead > 0 || cacheWrite > 0 ? (
          <>
            <span>{t('billing.cacheTokens')}</span>
            <span className="tabular-nums text-[var(--console-ink)]">
              {t('billing.cacheReadWrite', { read: cacheRead, write: cacheWrite })}
            </span>
          </>
        ) : null}
        {models.length > 0 ? (
          <>
            <span>{t('billing.modelsUsed')}</span>
            <span className="truncate text-[var(--console-ink)]" title={models.join(', ')}>
              {models.join(', ')}
            </span>
          </>
        ) : null}
        {billing.call_count != null && billing.call_count > 0 ? (
          <>
            <span>{t('billing.llmCalls')}</span>
            <span className="tabular-nums text-[var(--console-ink)]">{billing.call_count}</span>
          </>
        ) : null}
        {billing.pricing_version != null ? (
          <>
            <span>{t('billing.pricingVersion')}</span>
            <span className="text-[var(--console-ink)]">v{billing.pricing_version}</span>
          </>
        ) : null}
        {(billing.cache_savings_credits ?? 0) > 0 ? (
          <>
            <span>{t('billing.cacheSavings')}</span>
            <span className="tabular-nums text-[var(--console-green)]">
              {fmtCredits(billing.cache_savings_credits ?? 0)} cr
            </span>
          </>
        ) : null}
      </div>
      {billing.interrupted && billing.interrupt_reason ? (
        <p className="mt-1.5 text-[var(--console-amber)]">{billing.interrupt_reason}</p>
      ) : null}
    </div>
  );
}
