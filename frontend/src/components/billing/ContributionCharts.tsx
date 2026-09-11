/**
 * 貢獻積分圖表區 — 池分布、鎖倉進度、獎勵預估、收益時序、半衰期、動態閾值
 */
import { useMemo, useState, type ReactNode } from 'react';
import LcBarChart from '../charts/LcBarChart';
import LcGaugeChart from '../charts/LcGaugeChart';
import LcLineChart from '../charts/LcLineChart';
import LcPieChart from '../charts/LcPieChart';
import LockTimelineChart from './LockTimelineChart';
import { consoleLayout } from '../../lib/consoleLayout';
import {
  contributionPoolSlices,
  decayProjection,
  earningsTimeSeries,
  rewardProjection,
  sumContributionPurchased,
  type PoolLedgerRow,
} from '../../lib/billingChartData';
import { fmtCredits } from '../../lib/billingUi';
import type { ContributionStatus } from '../../types';

export interface LockPreview {
  amount: number;
  days: number;
  multiplier: number;
}

export default function ContributionCharts({
  contribution,
  poolLedger,
  lockPreview,
}: {
  contribution: ContributionStatus;
  poolLedger: PoolLedgerRow[];
  lockPreview: LockPreview;
}) {
  const installments = contribution.installments ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(installments[0]?.installment_id ?? null);
  const selected =
    installments.find((i) => i.installment_id === selectedId) ?? installments[0] ?? null;

  const purchasedFromContribution = sumContributionPurchased(poolLedger);
  const poolSlices = useMemo(
    () => contributionPoolSlices(contribution, purchasedFromContribution),
    [contribution, purchasedFromContribution],
  );
  const hasPoolData = poolSlices.some((s) => s.value > 0);

  const projection = rewardProjection(lockPreview.amount, lockPreview.days, lockPreview.multiplier);
  const earnings = earningsTimeSeries(poolLedger);
  const decayPoints = decayProjection(contribution.unlocked, 12);

  const earningsCategories = earnings.length > 0 ? earnings.map((e) => e.label.slice(5)) : ['—'];
  const earningsGroups = earnings.length > 0
    ? [
        { subCategory: '入帳', values: earnings.map((e) => e.inflow) },
        { subCategory: '扣出', values: earnings.map((e) => e.outflow) },
      ]
    : [{ subCategory: '暫無資料', values: [0] }];

  const decaySeries = [
    {
      id: 'unlocked',
      name: '未鎖定餘額',
      color: '#64D2FF',
      points: decayPoints.map((p) => ({ x: p.month, y: p.value })),
    },
  ];

  return (
    <section className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
      <h3 className="shrink-0 text-[13px] font-medium text-[#F5F5F7]">圖表分析</h3>
      <div className={`${consoleLayout.cardGridFill} grid-cols-1 lg:grid-cols-2`}>
        {/* 1. 貢獻池分布 */}
        <ChartCard title="貢獻池分布" subtitle="未鎖 / 可轉鎖 / 已鎖 / 已轉已購買">
          <LcPieChart slices={poolSlices} height={220} emptyLabel="暫無貢獻積分" />
          {!hasPoolData ? <EmptyHint>尚無鎖倉或轉換紀錄</EmptyHint> : null}
        </ChartCard>

        {/* 6. 動態閾值儀表 */}
        <ChartCard
          title="動態鎖倉閾值"
          subtitle={`累積 ${fmtCredits(contribution.accumulated_unlocked)} / 閾值 ${fmtCredits(contribution.convert_threshold)}`}
        >
          <LcGaugeChart
            value={contribution.accumulated_unlocked}
            max={Math.max(contribution.convert_threshold, contribution.accumulated_unlocked, 1)}
            label="累積 / 閾值"
            sublabel={`剩餘 ${fmtCredits(contribution.convertible_to_locked)} 可轉鎖倉`}
            height={200}
          />
        </ChartCard>

        {/* 2. 鎖倉分期時間軸 */}
        <ChartCard title="鎖倉分期進度" subtitle="30 / 90 / 180 天 · 3 期解鎖標記">
          {installments.length > 1 ? (
            <select
              value={selected?.installment_id ?? ''}
              onChange={(e) => setSelectedId(e.target.value)}
              className="mb-2 w-full rounded border border-white/10 bg-black/30 px-2 py-1 text-[11px]"
            >
              {installments.map((i) => (
                <option key={i.installment_id} value={i.installment_id}>
                  {i.lock_days} 天 ×{i.lock_multiplier} · {i.progress_zh ?? ''}
                </option>
              ))}
            </select>
          ) : null}
          <LockTimelineChart installment={selected} />
        </ChartCard>

        {/* 3. 獎勵預估 vs 提前解鎖 */}
        <ChartCard
          title="獎勵預估"
          subtitle={`${fmtCredits(lockPreview.amount)} · ${lockPreview.days} 天 ×${lockPreview.multiplier}`}
        >
          <LcBarChart
            height={200}
            categories={['持有到期', '提前解鎖']}
            groups={[
              { subCategory: '本金', values: [projection.principal, projection.netIfEarly] },
              { subCategory: '獎勵', values: [projection.reward, 0] },
              { subCategory: '罰沒/罰金', values: [0, projection.earlyPenalty + projection.earlyForfeitReward] },
            ]}
          />
          <p className="mt-1 text-[10px] text-[#636366]">
            到期淨收益 {fmtCredits(projection.netIfHold)} · 提前解鎖淨退回 {fmtCredits(projection.netIfEarly)}
          </p>
        </ChartCard>

        {/* 4. 收益時序 */}
        <ChartCard title="貢獻收益時序" subtitle="池帳本入帳 / 扣出（近 14 日）">
          {earnings.length === 0 ? <EmptyHint>暫無資料 — 尚無貢獻帳本紀錄</EmptyHint> : null}
          <LcBarChart height={200} categories={earningsCategories} groups={earningsGroups} />
        </ChartCard>

        {/* 5. 半衰期衰減 */}
        <ChartCard title="未鎖定半衰期" subtitle={`每 ${3} 個月 ×0.8（預測）`}>
          {contribution.unlocked <= 0 ? <EmptyHint>暫無未鎖定餘額</EmptyHint> : null}
          <LcLineChart
            height={200}
            series={decaySeries}
          />
          <p className="mt-1 text-[10px] text-[#636366]">
            當前 {fmtCredits(contribution.unlocked)} → 12 月後約 {fmtCredits(decayPoints.at(-1)?.value ?? 0)}
          </p>
        </ChartCard>
      </div>
    </section>
  );
}

function ChartCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className={consoleLayout.insetCard}>
      <p className="text-[12px] font-medium text-[#F5F5F7]">{title}</p>
      {subtitle ? <p className={consoleLayout.meta}>{subtitle}</p> : null}
      <div className="mt-2">{children}</div>
    </div>
  );
}

function EmptyHint({ children }: { children: ReactNode }) {
  return <p className="mb-1 text-center text-[10px] text-[#636366]">{children}</p>;
}
