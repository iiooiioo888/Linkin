/**
 * 靈境積分中心 — OCD 三欄 dense 單頁（左導航 · 中 KPI/主表 · 右活動/快操）
 * 深鏈：#/monitor/credits/{section} · #/monitor/billing → cloud
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  assignBillingPlan,
  convertContribution,
  fetchBilling,
  fetchBillingOverview,
  fetchBillingAppeals,
  fetchBillingGrants,
  fetchBillingPoolLedger,
  fetchBillingRollover,
  fetchCloudBilling,
  lockContribution,
  submitBillingAppeal,
  bindContributorKey,
  fetchContributorEarnings,
  fetchContributorKeys,
  fetchContributorKeyHealth,
  triggerInstallments,
  topupBillingCredits,
} from '../../api/client';
import { useWallet } from '../../hooks/useWallet';
import {
  fmtCredits,
  formatUsageEventTokens,
  lockThresholdNotice,
  POOL_LABELS_ZH,
  rolloverNoticeZh,
  convertPreview,
  installmentProgress,
  CONTRIBUTION_EMPTY_ZH,
  CREDITS_SECTIONS,
  creditsAnchorId,
  jumpToCreditsSection,
  parseCreditsSection,
  type CreditsSectionKey,
} from '../../lib/billingUi';
import type {
  BillingAppeal,
  BillingGrant,
  BillingPoolsDetail,
  CloudBilling,
  ContributionStatus,
  PoolLedgerEntry,
} from '../../types';
import BillingAdminPanel from './BillingAdminPanel';
import ContributionCharts, { type LockPreview } from './ContributionCharts';
import { usePagination } from '../../lib/pagination';
import { ConsolePagination } from '../ui/ConsolePagination';
import {
  ConsoleCard,
  ConsoleCardBody,
  ConsoleCardHeader,
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  ConsoleGiantKpi,
  ConsoleLeftRail,
  ConsolePlanChip,
  ConsoleRailNav,
  ConsoleRightRail,
  ConsoleSnippetList,
  ConsoleThreeColumn,
  KpiCard,
  KpiGrid,
  PanelAlert,
  PanelShell,
  consoleLayout,
} from '../ui/ConsoleLayout';

const NAV_ITEMS = CREDITS_SECTIONS.map((s) => ({ id: s.anchorId, label: s.label }));

const EVENT_ZH: Record<string, string> = {
  llm_tokens: 'LLM',
  reflection_iter: '反思',
  raho_role: 'RAHO',
  docker_runtime: 'Docker',
  docker: 'Docker',
  topup: '充值',
  plan_quota: '配額',
};

function formatCost(amount: number): string {
  if (amount < 0.01) return `$${amount.toFixed(4)}`;
  if (amount < 1) return `$${amount.toFixed(3)}`;
  return `$${amount.toFixed(2)}`;
}

function sparkFromLedger(values: number[], count = 8): number[] {
  const slice = values.slice(0, count).reverse();
  while (slice.length < count) slice.unshift(0);
  return slice;
}

export default function BillingCreditsHub() {
  const [section, setSection] = useState<CreditsSectionKey>(() => parseCreditsSection());
  const wallet = useWallet(8000);

  const [pools, setPools] = useState<BillingPoolsDetail | null>(null);
  const [contribution, setContribution] = useState<ContributionStatus | null>(null);
  const [grants, setGrants] = useState<BillingGrant[]>([]);
  const [rollovers, setRollovers] = useState<Record<string, unknown>[]>([]);
  const [appeals, setAppeals] = useState<BillingAppeal[]>([]);
  const [poolLedger, setPoolLedger] = useState<PoolLedgerEntry[]>([]);
  const [cloudBilling, setCloudBilling] = useState<CloudBilling | null>(null);
  const [overview, setOverview] = useState<{
    monthly_used_credits: number;
    balance_credits: number;
    unhealthy_keys_count: number;
    period_key?: string;
  } | null>(null);
  const [lockPreview, setLockPreview] = useState<LockPreview>({ amount: 10, days: 30, multiplier: 1.02 });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [topupAmount, setTopupAmount] = useState('5000');

  const refresh = useCallback(async () => {
    try {
      const [billing, overviewResp, grantResp, rollResp, appealResp, ledgerResp, cloudResp] = await Promise.all([
        fetchBilling(),
        fetchBillingOverview().catch(() => null),
        fetchBillingGrants(30),
        fetchBillingRollover(20),
        fetchBillingAppeals(20),
        fetchBillingPoolLedger(50),
        fetchCloudBilling().catch(() => null),
      ]);
      if (overviewResp) setOverview(overviewResp);
      setPools(billing.pools ?? null);
      setContribution(billing.contribution ?? null);
      setGrants(grantResp.items);
      setRollovers(rollResp.items);
      setAppeals(appealResp.appeals);
      setPoolLedger(ledgerResp.items);
      if (cloudResp) setCloudBilling(cloudResp);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : '載入失敗');
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 30000);
    return () => clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    const onHash = () => setSection(parseCreditsSection());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const onNavSelect = (anchorId: string) => {
    const hit = CREDITS_SECTIONS.find((s) => s.anchorId === anchorId);
    if (hit) {
      jumpToCreditsSection(hit.key);
      setSection(hit.key);
    }
  };

  const grantsPager = usePagination(grants, 8);
  const rolloversPager = usePagination(rollovers, 6);
  const installmentsPager = usePagination(contribution?.installments ?? [], 4);
  const appealsListPager = usePagination(appeals, 6);

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      setMsg(ok);
      await refresh();
      await wallet.refresh();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : '操作失敗');
    } finally {
      setBusy(false);
    }
  };

  const poolBalances = Object.entries(pools?.balances ?? {});
  const totalPoolBalance = poolBalances.reduce((sum, [, v]) => sum + Number(v), 0);
  const balance = wallet.account?.balance_credits ?? 0;
  const usageSpark = sparkFromLedger(wallet.usage.map((u) => u.credits));
  const ledgerSpark = sparkFromLedger(wallet.ledger.map((l) => Math.abs(l.amount_credits)));

  const pendingAppeals = appeals.filter((a) => a.status === 'pending' || a.status === 'open');
  const activeInstallments = contribution?.installments?.filter((i) => i.status === 'active') ?? [];

  const centerContent = useMemo(() => {
    if (section === 'overview') {
      const monthSpend = overview?.monthly_used_credits ?? wallet.account?.monthly_used_credits ?? 0;
      const remainBal = overview?.balance_credits ?? balance;
      const badKeys = overview?.unhealthy_keys_count ?? 0;
      return (
        <div className={cnStack()}>
          <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
            <KpiCard
              label="本月消耗"
              value={`${fmtCredits(monthSpend)} cr`}
              hint={overview?.period_key ?? wallet.account?.period_key ?? '—'}
              accent
            />
            <KpiCard
              label="剩餘餘額"
              value={`${fmtCredits(remainBal)} cr`}
              hint={wallet.account?.low_balance ? '偏低' : '可用'}
            />
            {badKeys > 0 ? (
              <button type="button" className="text-left" onClick={() => onNavSelect('credits-contributor')}>
                <KpiCard label="異常 Key" value={`${badKeys} 個`} hint="點擊檢查貢獻者 Key" />
              </button>
            ) : (
              <KpiCard label="異常 Key" value="0 個" hint="健康" />
            )}
          </div>
          <div className={consoleLayout.giantKpiRow}>
            <ConsoleGiantKpi
              label="可用積分"
              value={wallet.loading && !wallet.account ? '—' : fmtCredits(balance)}
              unit="cr"
              meta={`方案 ${wallet.account?.plan_name_zh ?? '—'}`}
              accent
              spark={usageSpark}
            />
            <ConsoleGiantKpi
              label="月度贈送"
              value={fmtCredits(wallet.account?.pool_balances?.monthly_grant ?? 0)}
              unit="cr"
              meta={`已購買 ${fmtCredits(wallet.account?.pool_balances?.purchased ?? 0)}`}
              spark={[40, 55, 48, 62, 58, 70, 65, 72]}
            />
            <ConsoleGiantKpi
              label="Docker 已扣"
              value={fmtCredits(wallet.docker?.total_docker_credits_spent ?? 0)}
              unit="cr"
              meta={`${wallet.docker?.running_services?.filter((s) => s.is_mine).length ?? 0} 個運行中`}
              spark={ledgerSpark}
            />
          </div>
          <div className={consoleLayout.cardGridFill}>
            <ConsoleCard className="flex min-h-0 flex-col">
              <ConsoleCardHeader>訂閱方案</ConsoleCardHeader>
              <ConsoleCardBody dense className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto console-col-scroll">
                {(wallet.plans as { id: string; name_zh: string; monthly_credits: number; price_usd_month: number | null }[]).map((p) => {
                  const active = wallet.account?.plan_id === p.id;
                  return (
                    <div
                      key={p.id}
                      className={`flex items-center justify-between gap-2 rounded-lg border px-3 py-2 ${active ? 'border-[var(--console-accent)]/40 bg-[var(--console-card-elevated)]' : 'border-[var(--console-line)]'}`}
                    >
                      <div className="min-w-0">
                        <p className="text-[12px] font-medium text-[var(--console-ink)]">{p.name_zh}</p>
                        <p className="text-[10px] text-[var(--console-sub)]">
                          {p.price_usd_month != null ? `$${p.price_usd_month}/月` : '客製'} · {fmtCredits(p.monthly_credits)} 積分
                        </p>
                      </div>
                      {!active ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void run(() => assignBillingPlan(p.id), `已切換至 ${p.name_zh}`)}
                          className="shrink-0 text-[11px] text-[var(--console-blue)]"
                        >
                          切換
                        </button>
                      ) : (
                        <span className="text-[10px] text-[var(--console-accent)]">使用中</span>
                      )}
                    </div>
                  );
                })}
              </ConsoleCardBody>
            </ConsoleCard>
            <ConsoleCard className="flex min-h-0 flex-col">
              <ConsoleCardHeader>Docker 即時計費</ConsoleCardHeader>
              <ConsoleCardBody dense>
                <div className={consoleLayout.cardGrid}>
                  <KpiCard label="牌價時費" value={`${fmtCredits(wallet.docker?.projected_hourly_credits ?? 0)}/h`} />
                  <KpiCard label="超額時費" value={`${fmtCredits(wallet.docker?.projected_billable_hourly_credits ?? wallet.docker?.projected_hourly_credits ?? 0)}/h`} />
                  <KpiCard label="含額剩餘" value={`${wallet.docker?.plan_terms?.included_hours_remaining?.toFixed(1) ?? '0'} h`} />
                  <KpiCard label="倍率" value={`×${wallet.docker?.plan_terms?.rate_multiplier ?? '—'}`} />
                </div>
                <ul className="mt-2 space-y-1 text-[11px] text-[var(--console-sub)]">
                  {(wallet.docker?.running_services?.filter((s) => s.is_mine) ?? []).slice(0, 4).map((svc) => (
                    <li key={svc.service} className="flex justify-between gap-2">
                      <span className="truncate">{svc.service}</span>
                      <span className="shrink-0 tabular-nums">{fmtCredits(svc.credits_per_hour)}/h</span>
                    </li>
                  ))}
                </ul>
              </ConsoleCardBody>
            </ConsoleCard>
          </div>
          <ConsoleCard>
            <ConsoleCardHeader>最近用量</ConsoleCardHeader>
            <ConsoleCardBody dense>
              <table className="w-full text-left text-[11px]">
                <thead className="text-[var(--console-faint)]">
                  <tr>
                    <th className="pb-1">時間</th>
                    <th>類型</th>
                    <th>Token / 模型</th>
                    <th className="text-right">積分</th>
                  </tr>
                </thead>
                <tbody>
                  {wallet.usage.slice(0, 8).map((row) => (
                    <tr key={row.id} className="border-t border-[var(--console-line)]">
                      <td className="py-1 text-[var(--console-sub)]">{new Date(row.created_at).toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</td>
                      <td>{EVENT_ZH[row.event_type] ?? row.event_type}</td>
                      <td className="max-w-[140px] truncate text-[var(--console-sub)]" title={formatUsageEventTokens(row.meta)}>
                        {formatUsageEventTokens(row.meta)}
                      </td>
                      <td className="text-right tabular-nums console-status-accent">-{fmtCredits(row.credits)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ConsoleCardBody>
          </ConsoleCard>
        </div>
      );
    }

    if (section === 'cloud') {
      const b = cloudBilling;
      const breakdown = b?.breakdown;
      return (
        <div className={cnStack()}>
          <div className={consoleLayout.giantKpiRow}>
            <ConsoleGiantKpi label="今日費用" value={b ? formatCost(b.today_total) : '—'} meta="Docker＋阿里雲" spark={[20, 35, 28, 42, 38, 50, 45, b?.today_total ?? 0]} />
            <ConsoleGiantKpi label="本月費用" value={b ? formatCost(b.month_total) : '—'} meta="雲資源 USD" accent spark={[30, 45, 40, 55, 50, 60, 58, b?.month_total ?? 0]} />
            <ConsoleGiantKpi label="即時合計" value={b ? formatCost(b.total_now) : '—'} meta="累計雲資源" spark={[25, 38, 32, 48, 44, 52, 50, b?.total_now ?? 0]} />
          </div>
          <div className={consoleLayout.cardGrid}>
            <ConsoleCard>
              <ConsoleCardHeader>費用組成</ConsoleCardHeader>
              <ConsoleCardBody dense>
                <div className={consoleLayout.cardGrid}>
                  <KpiCard label="Docker" value={breakdown ? formatCost(breakdown.docker_usd) : '—'} valueClassName="console-status-blue" />
                  <KpiCard label="阿里雲" value={breakdown ? formatCost(breakdown.aliyun_usd) : '—'} valueClassName="console-status-amber" />
                  <KpiCard label="小計" value={breakdown ? formatCost(breakdown.cloud_total_usd) : '—'} valueClassName="console-status-green" />
                </div>
              </ConsoleCardBody>
            </ConsoleCard>
            <ConsoleCard>
              <ConsoleCardHeader>阿里雲 BSS</ConsoleCardHeader>
              <ConsoleCardBody dense>
                {b?.aliyun?.configured ? (
                  <div className={consoleLayout.cardGrid}>
                    <KpiCard label="本月 CNY" value={`¥${b.aliyun.month_total_cny.toFixed(2)}`} />
                    <KpiCard label="本月 USD" value={formatCost(b.aliyun.month_total_usd)} />
                  </div>
                ) : (
                  <p className="text-[11px] text-[var(--console-sub)]">未配置 AccessKey · 設定 ALIYUN_ACCESS_KEY_ID</p>
                )}
              </ConsoleCardBody>
            </ConsoleCard>
          </div>
          <ConsoleCard className="flex min-h-0 flex-1 flex-col">
            <ConsoleCardHeader>各服務費用</ConsoleCardHeader>
            <ConsoleCardBody dense className="flex min-h-0 flex-1 flex-col">
              <div className="grid min-h-0 flex-1 gap-2 overflow-y-auto console-col-scroll sm:grid-cols-2">
                {(b?.per_service ?? []).slice(0, 8).map((svc) => (
                  <div key={`${svc.source}-${svc.service}`} className={consoleLayout.insetCard}>
                    <div className="flex items-start justify-between gap-2">
                      <p className="truncate text-[12px] text-[var(--console-ink)]">{svc.product_name || svc.service}</p>
                      <span className="shrink-0 font-mono text-[12px] console-status-amber">{formatCost(svc.cost)}</span>
                    </div>
                    <p className="mt-1 text-[10px] text-[var(--console-faint)]">{svc.source === 'aliyun' ? '阿里雲' : 'Docker'}</p>
                  </div>
                ))}
              </div>
            </ConsoleCardBody>
          </ConsoleCard>
        </div>
      );
    }

    if (section === 'pools') {
      return (
        <div className={cnStack()}>
          <KpiGrid fill>
            {poolBalances.map(([k, v]) => (
              <KpiCard key={k} label={POOL_LABELS_ZH[k] ?? k} value={fmtCredits(v)} spark={[v * 0.6, v * 0.7, v * 0.65, v * 0.8, v * 0.75, v * 0.9, v * 0.85, v]} />
            ))}
            {poolBalances.length > 0 ? (
              <KpiCard label="池內合計" value={fmtCredits(totalPoolBalance)} hint={`${poolBalances.length} 個池`} />
            ) : null}
          </KpiGrid>
          <div className={consoleLayout.cardGridFill}>
            <ConsoleCard className="flex min-h-0 flex-col">
              <ConsoleCardHeader>入帳來源</ConsoleCardHeader>
              <ConsoleCardBody dense className="flex min-h-0 flex-1 flex-col">
                <table className="w-full text-left text-[11px]">
                  <thead className="text-[var(--console-faint)]">
                    <tr><th className="py-1">池</th><th>來源</th><th>origin</th><th>餘額</th></tr>
                  </thead>
                  <tbody>
                    {grantsPager.slice.map((g) => (
                      <tr key={g.grant_id} className="border-t border-[var(--console-line)]">
                        <td className="py-1">{POOL_LABELS_ZH[g.pool_type] ?? g.pool_type}</td>
                        <td>{g.source}</td>
                        <td className="console-status-blue">{g.origin || '—'}</td>
                        <td className="tabular-nums">{fmtCredits(g.remaining)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <ConsolePagination page={grantsPager.page} totalPages={grantsPager.pages} onPageChange={grantsPager.setPage} className="!border-0" />
              </ConsoleCardBody>
            </ConsoleCard>
            <ConsoleCard className="flex min-h-0 flex-col">
              <ConsoleCardHeader>滾存紀錄</ConsoleCardHeader>
              <ConsoleCardBody dense className="flex min-h-0 flex-1 flex-col">
                <table className="w-full text-left text-[11px]">
                  <thead className="text-[var(--console-faint)]">
                    <tr><th>月份</th><th>未用</th><th>滾入</th><th>作廢</th></tr>
                  </thead>
                  <tbody>
                    {rolloversPager.slice.map((r, i) => (
                      <tr key={i} className="border-t border-[var(--console-line)]">
                        <td>{String(r.month_key)}</td>
                        <td>{fmtCredits(Number(r.unused_monthly))}</td>
                        <td className="console-status-green">{fmtCredits(Number(r.rolled_to_purchased))}</td>
                        <td className="console-status-accent">{fmtCredits(Number(r.forfeited))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <ConsolePagination page={rolloversPager.page} totalPages={rolloversPager.pages} onPageChange={rolloversPager.setPage} className="!border-0" />
              </ConsoleCardBody>
            </ConsoleCard>
          </div>
        </div>
      );
    }

    if (section === 'contribution' && contribution) {
      return (
        <div className={cnStack()}>
          <div className="shrink-0 rounded-lg border border-[var(--console-blue)]/20 bg-[var(--console-blue)]/5 px-3 py-2 text-[11px] text-[var(--console-sub)]">
            {contribution.notice_zh ?? lockThresholdNotice(contribution.accumulated_unlocked, contribution.convert_threshold, contribution.convertible_to_locked)}
          </div>
          <div className={consoleLayout.cardGridFill}>
            <ConsoleCard className="flex min-h-0 flex-col">
              <ConsoleCardHeader>未鎖定 → 已購買</ConsoleCardHeader>
              <ConsoleCardBody>
                <ConvertForm max={contribution.unlocked} empty={contribution.unlocked <= 0} preview={(a) => convertPreview(a, contribution.convert_ratio_to_purchased)} onSubmit={(a) => run(() => convertContribution(a), `已轉換 ${fmtCredits(a)}`)} busy={busy} />
              </ConsoleCardBody>
            </ConsoleCard>
            <ConsoleCard className="flex min-h-0 flex-col">
              <ConsoleCardHeader>轉鎖倉</ConsoleCardHeader>
              <ConsoleCardBody>
                <LockForm max={contribution.convertible_to_locked} empty={contribution.convertible_to_locked <= 0} tiers={contribution.lock_tiers} onPreviewChange={setLockPreview} onSubmit={(amount, days) => run(() => lockContribution(amount, days), `已鎖倉 ${fmtCredits(amount)}`)} busy={busy} />
              </ConsoleCardBody>
            </ConsoleCard>
          </div>
          <ConsoleCard className="flex min-h-0 flex-1 flex-col">
            <ConsoleCardHeader>圖表與分期</ConsoleCardHeader>
            <ConsoleCardBody dense className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
              <ContributionCharts contribution={contribution} poolLedger={poolLedger} lockPreview={lockPreview} />
              <ul className="space-y-1 text-[11px]">
                {installmentsPager.slice.map((ins) => (
                  <li key={ins.installment_id} className="rounded-lg border border-[var(--console-line)] px-3 py-2">
                    <span className="text-[var(--console-ink)]">{ins.lock_days} 天 ×{ins.lock_multiplier}</span>
                    <span className="ml-2 text-[var(--console-sub)]">{installmentProgress(ins.paid_installments)}</span>
                  </li>
                ))}
              </ul>
              <ConsolePagination page={installmentsPager.page} totalPages={installmentsPager.pages} onPageChange={installmentsPager.setPage} className="!border-0" />
            </ConsoleCardBody>
          </ConsoleCard>
        </div>
      );
    }

    if (section === 'contributor') {
      return (
        <ConsoleCard className="flex min-h-0 flex-1 flex-col">
          <ConsoleCardHeader>貢獻者 · Key 綁定</ConsoleCardHeader>
          <ConsoleCardBody className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <ContributorPanel onMsg={setMsg} busy={busy} setBusy={setBusy} />
          </ConsoleCardBody>
        </ConsoleCard>
      );
    }

    if (section === 'appeals') {
      return (
        <div className={cnStack()}>
          <ConsoleCard>
            <ConsoleCardHeader>提交申訴</ConsoleCardHeader>
            <ConsoleCardBody>
              <AppealForm forfeitedInstallments={(contribution?.installments ?? []).filter((i) => i.status === 'forfeited_key_failure' && i.appeal_deadline)} onSubmit={(r, d, t, kind, installmentId) => run(() => submitBillingAppeal(r, d, t, { appealKind: kind, installmentId }), '申訴已提交')} busy={busy} />
            </ConsoleCardBody>
          </ConsoleCard>
          <ConsoleCard className="flex min-h-0 flex-1 flex-col">
            <ConsoleCardHeader>申訴紀錄</ConsoleCardHeader>
            <ConsoleCardBody dense className="flex min-h-0 flex-1 flex-col">
              <ul className="space-y-2 text-[11px]">
                {appealsListPager.slice.map((a) => (
                  <li key={a.appeal_id} className="rounded-lg border border-[var(--console-line)] px-3 py-2">
                    <span className="text-[var(--console-ink)]">{a.reason}</span>
                    <span className="ml-2 text-[var(--console-sub)]">{a.status}</span>
                  </li>
                ))}
              </ul>
              <ConsolePagination page={appealsListPager.page} totalPages={appealsListPager.pages} onPageChange={appealsListPager.setPage} className="!border-0" />
            </ConsoleCardBody>
          </ConsoleCard>
        </div>
      );
    }

    if (section === 'admin') {
      return (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <BillingAdminPanel onMsg={setMsg} embedded />
        </div>
      );
    }

    return null;
  }, [
    section, wallet, balance, usageSpark, ledgerSpark, busy, cloudBilling, poolBalances,
    totalPoolBalance, grantsPager, rolloversPager, contribution, installmentsPager,
    appealsListPager, poolLedger, lockPreview,
  ]);

  const rightContent = useMemo(() => {
    if (section === 'overview') {
      return (
        <>
          <ConsoleSnippetList title="快速充值">
            <div className="flex gap-2">
              <input type="number" value={topupAmount} onChange={(e) => setTopupAmount(e.target.value)} className="min-w-0 flex-1 rounded border border-[var(--console-line)] bg-[var(--console-bg)] px-2 py-1 text-[11px]" />
              <button type="button" disabled={busy} onClick={() => void run(() => topupBillingCredits(Number(topupAmount)), '充值成功')} className="shrink-0 text-[11px] text-[var(--console-blue)]">充值</button>
            </div>
          </ConsoleSnippetList>
          <ConsoleSnippetList title="分類帳">
            {wallet.ledger.slice(0, 5).map((row) => (
              <div key={row.id} className={consoleLayout.snippetRow}>
                <span className="text-[var(--console-sub)]">{EVENT_ZH[row.source] ?? row.source}</span>
                <span className={`tabular-nums ${row.amount_credits < 0 ? 'console-status-accent' : 'console-status-green'}`}>
                  {row.amount_credits > 0 ? '+' : ''}{fmtCredits(row.amount_credits)}
                </span>
              </div>
            ))}
          </ConsoleSnippetList>
          {wallet.account?.low_balance ? (
            <PanelAlert tone="error">積分偏低，請充值或升級方案</PanelAlert>
          ) : null}
        </>
      );
    }
    if (section === 'cloud') {
      const aliyun = cloudBilling?.aliyun;
      return (
        <>
          <ConsoleSnippetList title="接入狀態">
            <div className={consoleLayout.snippetRow}>
              <span>Docker</span>
              <span className="console-status-green">運行中</span>
            </div>
            <div className={consoleLayout.snippetRow}>
              <span>阿里雲 BSS</span>
              <span className={aliyun?.configured && aliyun.ok ? 'console-status-green' : 'console-status-amber'}>
                {aliyun?.configured && aliyun.ok ? '已連線' : aliyun?.configured ? '查詢失敗' : '未接入'}
              </span>
            </div>
          </ConsoleSnippetList>
          <ConsoleSnippetList title="月度預估">
            <p className="text-[24px] tabular-nums text-[var(--console-ink)]">{cloudBilling ? formatCost(cloudBilling.month_projected) : '—'}</p>
            <p className="text-[10px] text-[var(--console-faint)]">依 Docker 小時費率推估</p>
          </ConsoleSnippetList>
        </>
      );
    }
    if (section === 'pools') {
      return (
        <>
          {pools?.cache_stats ? (
            <ConsoleSnippetList title="L3 快取">
              <div className={consoleLayout.snippetRow}>
                <span>節省</span>
                <span className="console-status-green">{fmtCredits(pools.cache_stats.savings_credits)}</span>
              </div>
              <div className={consoleLayout.snippetRow}>
                <span>命中</span>
                <span>{pools.cache_stats.l3_hits} 次</span>
              </div>
            </ConsoleSnippetList>
          ) : null}
          <ConsoleSnippetList title="滾存政策">
            <p className="text-[11px] text-[var(--console-sub)]">{pools?.rollover_notice_zh ?? rolloverNoticeZh(0.5, 50000)}</p>
          </ConsoleSnippetList>
        </>
      );
    }
    if (section === 'contribution') {
      return (
        <>
          <ConsoleSnippetList title="鎖倉進度">
            {activeInstallments.length === 0 ? (
              <p className="text-[11px] text-[var(--console-sub)]">尚無進行中分期</p>
            ) : (
              activeInstallments.slice(0, 4).map((ins) => (
                <div key={ins.installment_id} className={consoleLayout.snippetRow}>
                  <span>{ins.lock_days} 天</span>
                  <span>{installmentProgress(ins.paid_installments)}</span>
                </div>
              ))
            )}
          </ConsoleSnippetList>
          <button type="button" disabled={busy} onClick={() => void run(() => triggerInstallments(false), '已處理到期分期')} className="w-full rounded-lg border border-[var(--console-line)] py-2 text-[11px] text-[var(--console-blue)]">
            處理到期分期
          </button>
        </>
      );
    }
    if (section === 'appeals') {
      return (
        <ConsoleSnippetList title="待處理申訴">
          {pendingAppeals.length === 0 ? (
            <p className="text-[11px] text-[var(--console-sub)]">無待處理</p>
          ) : (
            pendingAppeals.slice(0, 5).map((a) => (
              <div key={a.appeal_id} className={consoleLayout.snippetRow}>
                <span className="truncate">{a.reason}</span>
                <span className="console-status-amber">{a.status}</span>
              </div>
            ))
          )}
        </ConsoleSnippetList>
      );
    }
    return (
      <ConsoleSnippetList title="管理提示">
        <p className="text-[11px] text-[var(--console-sub)]">定價、政策、Fault Pool 與路由需 Admin Secret</p>
      </ConsoleSnippetList>
    );
  }, [section, wallet, topupAmount, busy, cloudBilling, pools, activeInstallments, pendingAppeals]);

  return (
    <PanelShell scroll={false}>
      <ConsoleThreeColumn>
        <ConsoleLeftRail>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-4">
            <h1 className="text-[15px] font-semibold text-[var(--console-ink)]">靈境積分</h1>
            <p className="mt-1 text-[10px] text-[var(--console-faint)]">計費 · Docker · 阿里雲</p>
          </div>
          <ConsoleColumnScroll className="!px-0 !py-0">
            <ConsoleRailNav
              sections={NAV_ITEMS}
              activeId={creditsAnchorId(section)}
              onSelect={onNavSelect}
            />
          </ConsoleColumnScroll>
          <div className="shrink-0 border-t border-[var(--console-line)] px-3 py-3">
            <p className="mb-2 text-[10px] uppercase tracking-wider text-[var(--console-faint)]">方案</p>
            <div className="flex flex-wrap gap-1">
              {(wallet.plans as { id: string; name_zh: string }[]).slice(0, 4).map((p) => (
                <ConsolePlanChip
                  key={p.id}
                  label={p.name_zh}
                  active={wallet.account?.plan_id === p.id}
                  onClick={wallet.account?.plan_id === p.id ? undefined : () => void run(() => assignBillingPlan(p.id), `已切換至 ${p.name_zh}`)}
                />
              ))}
            </div>
          </div>
        </ConsoleLeftRail>

        <ConsoleCenterColumn>
          {msg ? (
            <div className="shrink-0 px-4 pt-2">
              <PanelAlert tone="notice">{msg}</PanelAlert>
            </div>
          ) : null}
          <ConsoleColumnScroll>{centerContent}</ConsoleColumnScroll>
        </ConsoleCenterColumn>

        <ConsoleRightRail>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-3">
            <p className="text-[11px] font-semibold text-[var(--console-ink)]">活動與快操</p>
            <p className="text-[10px] text-[var(--console-faint)]">
              {CREDITS_SECTIONS.find((s) => s.key === section)?.label ?? '總覽'}
            </p>
          </div>
          <ConsoleColumnScroll>
            <div className={consoleLayout.sectionStack}>{rightContent}</div>
          </ConsoleColumnScroll>
        </ConsoleRightRail>
      </ConsoleThreeColumn>
    </PanelShell>
  );
}

function cnStack() {
  return cn('flex min-h-0 flex-1 flex-col gap-2 overflow-hidden');
}

function cn(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ');
}

function ConvertForm({
  max, empty, preview, onSubmit, busy,
}: {
  max: number; empty?: boolean; preview: (a: number) => number;
  onSubmit: (a: number) => void; busy: boolean;
}) {
  const [amount, setAmount] = useState('10');
  const a = Number(amount);
  const disabled = busy || Boolean(empty) || a <= 0 || a > max;
  return (
    <div className="space-y-2">
      {empty ? <p className="rounded border border-[var(--console-amber)]/20 bg-[var(--console-amber)]/5 px-2 py-1.5 text-[11px] text-[var(--console-amber)]">{CONTRIBUTION_EMPTY_ZH}</p> : null}
      <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} disabled={empty} className="w-full rounded border border-[var(--console-line)] bg-[var(--console-bg)] px-2 py-1 text-[12px] disabled:opacity-40" />
      <p className="text-[10px] text-[var(--console-faint)]">預覽 {fmtCredits(preview(a))} 已購買（最多 {fmtCredits(max)}）</p>
      <button type="button" disabled={disabled} onClick={() => onSubmit(a)} className="text-[12px] text-[var(--console-blue)] disabled:opacity-40">轉換</button>
    </div>
  );
}

function LockForm({
  max, empty, tiers, onSubmit, onPreviewChange, busy,
}: {
  max: number; empty?: boolean; tiers: Record<string, number>;
  onSubmit: (a: number, d: number) => void; onPreviewChange: (p: LockPreview) => void; busy: boolean;
}) {
  const [amount, setAmount] = useState('10');
  const [days, setDays] = useState(30);
  const a = Number(amount);
  const mult = Number(tiers[String(days)] ?? tiers[days] ?? 1.02);
  const disabled = busy || Boolean(empty) || a <= 0 || a > max;
  useEffect(() => {
    onPreviewChange({ amount: a, days, multiplier: mult });
  }, []);
  return (
    <div className="space-y-2">
      {empty ? <p className="rounded border border-[var(--console-amber)]/20 bg-[var(--console-amber)]/5 px-2 py-1.5 text-[11px] text-[var(--console-amber)]">{CONTRIBUTION_EMPTY_ZH}</p> : null}
      <input type="number" value={amount} disabled={empty} onChange={(e) => { setAmount(e.target.value); onPreviewChange({ amount: Number(e.target.value), days, multiplier: mult }); }} className="w-full rounded border border-[var(--console-line)] bg-[var(--console-bg)] px-2 py-1 text-[12px] disabled:opacity-40" />
      <select value={days} disabled={empty} onChange={(e) => { const d = Number(e.target.value); setDays(d); onPreviewChange({ amount: a, days: d, multiplier: Number(tiers[String(d)] ?? 1.02) }); }} className="w-full rounded border border-[var(--console-line)] bg-[var(--console-bg)] px-2 py-1 text-[12px] disabled:opacity-40">
        {Object.entries(tiers).map(([d, m]) => <option key={d} value={d}>{d} 天 · ×{m}</option>)}
      </select>
      <p className="text-[10px] text-[var(--console-faint)]">預估獎勵 ×{mult}</p>
      <button type="button" disabled={disabled} onClick={() => onSubmit(a, days)} className="text-[12px] text-[var(--console-blue)] disabled:opacity-40">鎖倉</button>
    </div>
  );
}

function AppealForm({
  onSubmit, busy, forfeitedInstallments,
}: {
  onSubmit: (reason: string, detail: string, taskId: string, kind: string, installmentId: string) => void;
  busy: boolean;
  forfeitedInstallments: import('../../types').LockInstallment[];
}) {
  const [reason, setReason] = useState('');
  const [detail, setDetail] = useState('');
  const [kind, setKind] = useState('general');
  const [installmentId, setInstallmentId] = useState('');
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <select value={kind} onChange={(e) => setKind(e.target.value)} className="rounded border border-[var(--console-line)] bg-[var(--console-bg)] px-2 py-1 text-[12px]">
          <option value="general">一般申訴</option>
          <option value="key_failure_forfeiture">Key 故障沒收</option>
        </select>
        {kind === 'key_failure_forfeiture' ? (
          <select value={installmentId} onChange={(e) => setInstallmentId(e.target.value)} className="min-w-[12rem] rounded border border-[var(--console-line)] bg-[var(--console-bg)] px-2 py-1 text-[12px]">
            <option value="">選擇分期</option>
            {forfeitedInstallments.map((i) => <option key={i.installment_id} value={i.installment_id}>{i.installment_id.slice(-8)}</option>)}
          </select>
        ) : null}
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input placeholder="申訴原因" value={reason} onChange={(e) => setReason(e.target.value)} className="flex-1 rounded border border-[var(--console-line)] bg-[var(--console-bg)] px-2 py-1 text-[12px]" />
        <input placeholder="詳情" value={detail} onChange={(e) => setDetail(e.target.value)} className="flex-1 rounded border border-[var(--console-line)] bg-[var(--console-bg)] px-2 py-1 text-[12px]" />
        <button type="button" disabled={busy || !reason.trim() || (kind === 'key_failure_forfeiture' && !installmentId)} onClick={() => onSubmit(reason, detail, '', kind, installmentId)} className="text-[12px] text-[var(--console-blue)]">提交</button>
      </div>
    </div>
  );
}

function ContributorPanel({
  onMsg, busy, setBusy,
}: {
  onMsg: (m: string) => void; busy: boolean; setBusy: (b: boolean) => void;
}) {
  const [earnings, setEarnings] = useState<Record<string, unknown> | null>(null);
  const [keys, setKeys] = useState<Record<string, unknown>[]>([]);
  const [keyVal, setKeyVal] = useState('');
  const vendorId = 'self_host';
  const orgId = '';
  const dailyCap = '1000000';
  const concurrency = '2';

  const refresh = useCallback(async () => {
    const [e, k] = await Promise.all([fetchContributorEarnings(), fetchContributorKeys()]);
    setEarnings(e);
    setKeys((k.items as Record<string, unknown>[]) ?? []);
  }, []);

  useEffect(() => {
    void refresh().catch((err) => onMsg(err instanceof Error ? err.message : String(err)));
  }, [refresh, onMsg]);

  const keysPager = usePagination(keys, 5);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
      <KpiGrid>
        <KpiCard label="未鎖收益" value={fmtCredits(Number(earnings?.unlocked_earnings ?? 0))} />
        <KpiCard label="鎖倉收益" value={fmtCredits(Number(earnings?.locked_earnings ?? 0))} />
        <KpiCard label="已綁 Key" value={keys.length} />
      </KpiGrid>
      <div className="grid min-h-0 flex-1 gap-2 overflow-hidden lg:grid-cols-2">
        <div className={consoleLayout.insetCard}>
          <p className="mb-2 text-[11px] text-[var(--console-sub)]">綁定共享池 API Key（AES-256）</p>
          <input placeholder="API Key" value={keyVal} onChange={(e) => setKeyVal(e.target.value)} className="mb-2 w-full rounded border border-[var(--console-line)] bg-[var(--console-bg)] px-2 py-1.5 text-[12px]" />
          <button type="button" disabled={busy || keyVal.length < 8} className="text-[12px] text-[var(--console-blue)]" onClick={() => { setBusy(true); bindContributorKey(keyVal, { vendorId, orgId, dailyTokenCap: Number(dailyCap) || 0, concurrency: Number(concurrency) || 1, tosClass: vendorId === 'self_host' ? 'self_host' : 'resale_allowed', models: ['default'] }).then(() => { onMsg('Key 已綁定'); return refresh(); }).catch((e) => onMsg(e instanceof Error ? e.message : '失敗')).finally(() => setBusy(false)); }}>綁定 Key</button>
        </div>
        <div className={`${consoleLayout.insetCard} flex min-h-0 flex-col overflow-hidden`}>
          <p className="mb-2 text-[11px] font-medium text-[var(--console-ink)]">Key 健康度</p>
          <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto console-col-scroll text-[11px]">
            {keysPager.slice.map((k) => (
              <li key={String(k.key_id)} className="flex items-center justify-between gap-2 border-b border-[var(--console-line)] py-1">
                <span className="font-mono text-[var(--console-sub)]">{String(k.key_id).slice(-8)}</span>
                <button type="button" className="text-[10px] text-[var(--console-blue)]" onClick={() => void fetchContributorKeyHealth(String(k.key_id)).then((h) => onMsg(`成功率 ${(Number(h.success_rate) * 100).toFixed(1)}%`))}>檢查</button>
              </li>
            ))}
          </ul>
          <ConsolePagination page={keysPager.page} totalPages={keysPager.pages} onPageChange={keysPager.setPage} className="!border-0" />
        </div>
      </div>
    </div>
  );
}
