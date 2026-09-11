/**
 * WalletBadge — 頂欄／狀態列餘額徽章（輪詢更新）。
 */
import { useWallet } from '../hooks/useWallet';

interface WalletBadgeProps {
  onOpenBilling?: () => void;
  compact?: boolean;
  /** 行動端頂欄：僅顯示數值，避免與導覽搶寬度 */
  minimal?: boolean;
}

export default function WalletBadge({ onOpenBilling, compact = false, minimal = false }: WalletBadgeProps) {
  const { account } = useWallet(compact ? 12000 : 8000);
  const credits = account?.balance_credits ?? null;
  const low = account?.low_balance ?? false;

  if (credits === null) return null;

  const label = credits >= 10000 ? `${(credits / 1000).toFixed(1)}k` : credits.toFixed(0);

  return (
    <button
      type="button"
      onClick={onOpenBilling}
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] tabular-nums transition-colors ${
        low
          ? 'border-[color-mix(in_srgb,var(--console-amber)_35%,transparent)] bg-[color-mix(in_srgb,var(--console-amber)_10%,transparent)] console-status-amber hover:bg-[color-mix(in_srgb,var(--console-amber)_16%,transparent)]'
          : 'border-[color-mix(in_srgb,var(--console-accent)_35%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)] console-status-accent hover:bg-[color-mix(in_srgb,var(--console-accent)_16%,transparent)]'
      }`}
      title={low ? '積分偏低，點擊前往帳務中心' : '點擊查看靈境積分'}
    >
      <span className={low ? 'apple-dot apple-dot--warn' : 'apple-dot apple-dot--ok'} />
      {minimal ? label : compact ? `${label} 積分` : `積分 ${label}`}
    </button>
  );
}
