/**
 * 單輪用量：一行即可，不重複列出預估、定價版本或內部欄位。
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
  const input = billing.input_tokens ?? 0;
  const output = billing.output_tokens ?? 0;
  const hasTokens = input > 0 || output > 0;
  if (credits <= 0 && !hasTokens) return null;

  const parts: string[] = [];
  if (credits > 0) parts.push(`${t('billing.creditsCharged')} ${fmtCredits(credits)}`);
  if (hasTokens) parts.push(`${input} → ${output}`);

  return (
    <p className="mt-1.5 text-[11px] tabular-nums text-[var(--console-faint)]" data-testid="turn-billing-receipt">
      {parts.join(' · ')}
      {billing.interrupted && billing.interrupt_reason ? ` · ${billing.interrupt_reason}` : ''}
    </p>
  );
}
