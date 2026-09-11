/**
 * WalletBadge — 頂欄／狀態列餘額徽章（輪詢更新）。
 */
import { useWallet } from '../hooks/useWallet';

interface WalletBadgeProps {
  onOpenBilling?: () => void;
  compact?: boolean;
}

export default function WalletBadge({ onOpenBilling, compact = false }: WalletBadgeProps) {
  const { account } = useWallet(compact ? 12000 : 8000);
  const credits = account?.balance_credits ?? null;
  const low = account?.low_balance ?? false;

  if (credits === null) return null;

  const label = credits >= 10000 ? `${(credits / 1000).toFixed(1)}k` : credits.toFixed(0);

  return (
    <button
      type="button"
      onClick={onOpenBilling}
      className={`inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-[10px] tabular-nums ${
        low
          ? 'text-[#FF9F0A] hover:bg-[#FF9F0A]/10'
          : 'text-[#64D2FF] hover:bg-[#64D2FF]/10'
      }`}
      title={low ? '積分偏低，點擊前往帳務中心' : '點擊查看靈境積分'}
    >
      <span className={low ? 'apple-dot apple-dot--warn' : 'apple-dot apple-dot--ok'} />
      {compact ? `${label} 積分` : `積分 ${label}`}
    </button>
  );
}
