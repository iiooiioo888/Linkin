/**
 * 單輪調用資訊：僅 Token 流向。
 */
import type { ChatBillingMeta } from '../../lib/billingUi';

interface TurnBillingReceiptProps {
  billing: ChatBillingMeta;
}

export default function TurnBillingReceipt({ billing }: TurnBillingReceiptProps) {
  const input = billing.input_tokens ?? 0;
  const output = billing.output_tokens ?? 0;
  const hasTokens = input > 0 || output > 0;
  if (!hasTokens) return null;

  return (
    <p className="mt-1.5 text-[11px] tabular-nums text-[var(--console-faint)]" data-testid="turn-billing-receipt">
      Token {input} → {output}
      {billing.interrupted && billing.interrupt_reason ? ` · ${billing.interrupt_reason}` : ''}
    </p>
  );
}
