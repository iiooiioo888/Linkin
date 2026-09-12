/**
 * 輸入列旁積分餘額與預估消耗。
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useWallet } from '../../hooks/useWallet';
import { fmtCredits } from '../../lib/billingUi';
import type { SendOptions } from '../InputBar';

const MIN_SEND_CREDITS = 50;

function estimateCredits(text: string, strategy: SendOptions['executionStrategy']): number {
  const len = text.trim().length;
  if (strategy === 'simple') return Math.max(MIN_SEND_CREDITS, 80 + Math.round(len / 20));
  if (strategy === 'company') return Math.max(400, 500 + Math.round(len / 8));
  // auto
  if (len >= 200) return 600;
  if (len >= 80) return 250;
  return 120;
}

interface InputCreditBarProps {
  text: string;
  strategy: SendOptions['executionStrategy'];
  liveSpent?: number | null;
  onOpenBilling?: () => void;
}

export default function InputCreditBar({ text, strategy, liveSpent, onOpenBilling }: InputCreditBarProps) {
  const { t } = useTranslation();
  const { account, loading } = useWallet(10000);
  const balance = account?.balance_credits ?? null;
  const estimate = useMemo(() => estimateCredits(text, strategy), [text, strategy]);
  const low = account?.low_balance ?? false;
  const insufficient = balance !== null && balance < estimate;
  const blocked = balance !== null && balance <= 0;

  if (loading && balance === null) return null;

  return (
    <div
      className={`mb-2 flex flex-wrap items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 text-[10px] ${
        blocked || insufficient
          ? 'border-[color-mix(in_srgb,var(--console-danger)_35%,transparent)] bg-[color-mix(in_srgb,var(--console-danger)_8%,transparent)]'
          : low
            ? 'border-[color-mix(in_srgb,var(--console-amber)_30%,transparent)] bg-[color-mix(in_srgb,var(--console-amber)_8%,transparent)]'
            : 'border-white/[0.06] bg-white/[0.02]'
      }`}
      data-testid="input-credit-bar"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[var(--console-sub)]">
        <span>
          {t('chat.balance')}:{' '}
          <strong className={`tabular-nums ${low ? 'text-[var(--console-amber)]' : 'text-[var(--console-accent)]'}`}>
            {balance !== null ? fmtCredits(balance) : '—'}
          </strong>
          <span className="text-[var(--console-faint)]"> cr</span>
        </span>
        <span>
          {liveSpent != null && liveSpent > 0 ? t('chat.liveCost') : t('chat.estCost')}:{' '}
          <strong className="tabular-nums text-[var(--console-ink)]">
            {liveSpent != null && liveSpent > 0 ? fmtCredits(liveSpent) : fmtCredits(estimate)}
          </strong>
          <span className="text-[var(--console-faint)]"> cr</span>
        </span>
      </div>
      {(blocked || insufficient) && (
        <p className="text-[10px] console-status-danger">
          {blocked ? t('chat.insufficientBalance') : t('chat.lowBalanceWarn')}
        </p>
      )}
      {onOpenBilling && (
        <button
          type="button"
          onClick={onOpenBilling}
          className="ml-auto shrink-0 text-[10px] text-[var(--console-blue)] hover:underline"
        >
          {t('chat.openWallet')}
        </button>
      )}
    </div>
  );
}

export { estimateCredits, MIN_SEND_CREDITS };
