/** 貢獻積分圖表資料轉換（純函式，可單測）。 */

import type { ContributionStatus, LockInstallment } from '../types';

export const DECAY_HALF_LIFE_MONTHS = 3;
export const DECAY_FACTOR = 0.8;
export const EARLY_UNLOCK_PENALTY_RATIO = 0.05;

export interface PoolLedgerRow {
  id: string;
  amount_credits: number;
  kind: 'credit' | 'debit';
  source: string;
  pool_type?: string;
  created_at: string;
}

export function contributionPoolSlices(
  contribution: ContributionStatus,
  purchasedFromContribution = 0,
): Array<{ name: string; value: number; color: string }> {
  const thresholdReserve = Math.max(0, contribution.unlocked - contribution.convertible_to_locked);
  return [
    { name: '可轉鎖倉', value: contribution.convertible_to_locked, color: '#64D2FF' },
    { name: '閾值保留', value: thresholdReserve, color: '#8E8E93' },
    { name: '已鎖倉', value: contribution.locked, color: '#30D158' },
    { name: '已轉已購買', value: purchasedFromContribution, color: '#FF9F0A' },
  ];
}

export function lockTimelineMarkers(inst: LockInstallment | null): {
  days: number;
  markers: Array<{ day: number; label: string; paid: boolean }>;
  paidPct: number;
} {
  if (!inst) {
    return { days: 30, markers: [], paidPct: 0 };
  }
  const interval = inst.interval_days ?? Math.max(1, Math.floor(inst.lock_days / 3));
  const markers = [1, 2, 3].map((n) => ({
    day: interval * n,
    label: `第 ${n} 期`,
    paid: inst.paid_installments >= n,
  }));
  const paidPct = Math.round((inst.paid_installments / 3) * 100);
  return { days: inst.lock_days, markers, paidPct };
}

export function rewardProjection(
  amount: number,
  _lockDays: number,
  multiplier: number,
): {
  principal: number;
  reward: number;
  earlyPenalty: number;
  earlyForfeitReward: number;
  netIfHold: number;
  netIfEarly: number;
} {
  const principal = amount;
  const reward = amount * Math.max(0, multiplier - 1);
  const earlyPenalty = amount * EARLY_UNLOCK_PENALTY_RATIO;
  const earlyForfeitReward = reward;
  return {
    principal,
    reward,
    earlyPenalty,
    earlyForfeitReward,
    netIfHold: principal + reward,
    netIfEarly: principal - earlyPenalty,
  };
}

export function earningsTimeSeries(
  ledger: PoolLedgerRow[],
): Array<{ label: string; inflow: number; outflow: number }> {
  const contrib = ledger.filter(
    (e) =>
      e.pool_type?.includes('contribution') ||
      e.source.includes('contribution') ||
      e.source.includes('lock_') ||
      e.source.includes('reward'),
  );
  if (contrib.length === 0) return [];
  const byDay = new Map<string, { inflow: number; outflow: number }>();
  for (const row of contrib) {
    const day = row.created_at.slice(0, 10);
    const bucket = byDay.get(day) ?? { inflow: 0, outflow: 0 };
    const amt = Math.abs(row.amount_credits);
    if (row.kind === 'credit' || row.amount_credits > 0) bucket.inflow += amt;
    else bucket.outflow += amt;
    byDay.set(day, bucket);
  }
  return [...byDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-14)
    .map(([label, v]) => ({ label, ...v }));
}

export function decayProjection(unlocked: number, months = 12): Array<{ month: number; value: number }> {
  if (unlocked <= 0) {
    return Array.from({ length: months + 1 }, (_, i) => ({ month: i, value: 0 }));
  }
  const points: Array<{ month: number; value: number }> = [{ month: 0, value: unlocked }];
  let v = unlocked;
  for (let m = DECAY_HALF_LIFE_MONTHS; m <= months; m += DECAY_HALF_LIFE_MONTHS) {
    v = Math.round(v * DECAY_FACTOR * 10000) / 10000;
    points.push({ month: m, value: v });
  }
  return points;
}

export function sumContributionPurchased(ledger: PoolLedgerRow[]): number {
  return ledger
    .filter((e) => e.source === 'contribution_convert' && e.amount_credits > 0)
    .reduce((s, e) => s + e.amount_credits, 0);
}
