/**
 * 靈境積分中心 — 分頁切換：總覽 / 雲與 Docker / 積分池 / 貢獻 / 申訴 / 管理（無整頁滾動）
 * 深鏈：#/monitor/credits/{section} · #/monitor/billing → cloud
 */
import { useCallback, useEffect, useState } from 'react';
import {
  convertContribution,
  fetchBilling,
  fetchBillingAppeals,
  fetchBillingGrants,
  fetchBillingPoolLedger,
  fetchBillingRollover,
  lockContribution,
  submitBillingAppeal,
  bindContributorKey,
  fetchContributorEarnings,
  fetchContributorKeys,
  fetchContributorKeyHealth,
  triggerInstallments,
  earlyUnlockContribution,
} from '../../api/client';
import {
  fmtCredits,
  lockThresholdNotice,
  POOL_LABELS_ZH,
  rolloverNoticeZh,
  convertPreview,
  installmentProgress,
  installmentScheduleZh,
  earlyUnlockConfirmZh,
  keyFailureAppealNoticeZh,
  CONTRIBUTION_EMPTY_ZH,
  CREDITS_SECTIONS,
  creditsAnchorId,
  jumpToCreditsSection,
  parseCreditsSection,
  type CreditsSectionKey,
} from '../../lib/billingUi';
import type { BillingAppeal, BillingGrant, BillingPoolsDetail, ContributionStatus, PoolLedgerEntry } from '../../types';
import BillingPanel from '../BillingPanel';
import WalletPanel from '../WalletPanel';
import BillingAdminPanel from './BillingAdminPanel';
import ContributionCharts, { type LockPreview } from './ContributionCharts';
import { useFixedPages, usePagination } from '../../lib/pagination';
import { ConsolePageFrame, ConsolePagination } from '../ui/ConsolePagination';
import {
  ConsoleCard,
  ConsoleCardBody,
  ConsoleCardHeader,
  ConsoleSection,
  ConsoleSectionNav,
  ConsoleTabBody,
  KpiCard,
  KpiGrid,
  PanelAlert,
  PanelShell,
  SectionHeader,
  consoleLayout,
} from '../ui/ConsoleLayout';

const NAV_ITEMS = CREDITS_SECTIONS.map((s) => ({ id: s.anchorId, label: s.label }));

export default function BillingCreditsHub() {
  const [section, setSection] = useState<CreditsSectionKey>(() => parseCreditsSection());

  const [pools, setPools] = useState<BillingPoolsDetail | null>(null);
  const [contribution, setContribution] = useState<ContributionStatus | null>(null);
  const [grants, setGrants] = useState<BillingGrant[]>([]);
  const [rollovers, setRollovers] = useState<Record<string, unknown>[]>([]);
  const [appeals, setAppeals] = useState<BillingAppeal[]>([]);
  const [poolLedger, setPoolLedger] = useState<PoolLedgerEntry[]>([]);
  const [lockPreview, setLockPreview] = useState<LockPreview>({ amount: 10, days: 30, multiplier: 1.02 });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [billing, grantResp, rollResp, appealResp, ledgerResp] = await Promise.all([
        fetchBilling(),
        fetchBillingGrants(30),
        fetchBillingRollover(20),
        fetchBillingAppeals(20),
        fetchBillingPoolLedger(50),
      ]);
      setPools(billing.pools ?? null);
      setContribution(billing.contribution ?? null);
      setGrants(grantResp.items);
      setRollovers(rollResp.items);
      setAppeals(appealResp.appeals);
      setPoolLedger(ledgerResp.items);
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

  const poolsPager = useFixedPages(3);
  const grantsPager = usePagination(grants, 6);
  const rolloversPager = usePagination(rollovers, 6);
  const contributionPager = useFixedPages(3);
  const installmentsPager = usePagination(contribution?.installments ?? [], 3);
  const contributorPager = useFixedPages(2);
  const appealsPager = useFixedPages(2);
  const appealsListPager = usePagination(appeals, 5);

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      setMsg(ok);
      await refresh();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : '操作失敗');
    } finally {
      setBusy(false);
    }
  };

  const poolBalances = Object.entries(pools?.balances ?? {});
  const totalPoolBalance = poolBalances.reduce((sum, [, v]) => sum + Number(v), 0);

  const sectionBody = (
    <div className="min-h-0 flex-1 overflow-hidden">
      {section === 'overview' ? (
        <ConsoleSection id="credits-overview" title="總覽" description="方案、餘額、Docker 積分計費、用量與分類帳">
          <WalletPanel embedded />
        </ConsoleSection>
      ) : null}

      {section === 'cloud' ? (
        <ConsoleSection
          id="credits-cloud"
          title="雲與 Docker"
          description="Compose 容器按時 USD 計費 + 阿里雲 BSS 帳單（需 AccessKey）"
        >
          <BillingPanel embedded />
        </ConsoleSection>
      ) : null}

      {section === 'pools' ? (
        <ConsolePageFrame
          page={poolsPager.page}
          totalPages={poolsPager.pages}
          onPageChange={(p) => {
            poolsPager.setPage(p);
            if (p === 2) grantsPager.reset();
            if (p === 3) rolloversPager.reset();
          }}
        >
          <ConsoleSection
            id="credits-pools"
            title="積分池"
            description={pools?.rollover_notice_zh ?? rolloverNoticeZh(0.5, 50000)}
          >
            {poolsPager.page === 1 ? (
              <>
                <KpiGrid className="lg:grid-cols-3">
                  {poolBalances.map(([k, v]) => (
                    <KpiCard
                      key={k}
                      label={POOL_LABELS_ZH[k] ?? k}
                      value={fmtCredits(v)}
                      hint={k === 'monthly_grant' ? '月初滾存或作廢' : undefined}
                    />
                  ))}
                  {poolBalances.length > 0 ? (
                    <KpiCard label="池內合計" value={fmtCredits(totalPoolBalance)} hint={`${poolBalances.length} 個池`} />
                  ) : null}
                </KpiGrid>
                {pools?.cache_stats ? (
                  <div className={consoleLayout.insetCard}>
                    <p className="text-[11px] text-[#64D2FF]">
                      L3 快取累計節省 {fmtCredits(pools.cache_stats.savings_credits)} 積分 · 命中{' '}
                      {pools.cache_stats.l3_hits} 次
                    </p>
                  </div>
                ) : null}
              </>
            ) : null}

            {poolsPager.page === 2 ? (
              <ConsoleCard>
                <ConsoleCardHeader>入帳來源（origin）</ConsoleCardHeader>
                <ConsoleCardBody dense>
                  <table className="w-full text-left text-[11px]">
                    <thead className="text-[#8E8E93]">
                      <tr>
                        <th className="py-1">池</th>
                        <th>來源</th>
                        <th>origin</th>
                        <th>餘額</th>
                      </tr>
                    </thead>
                    <tbody>
                      {grantsPager.slice.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="py-4 text-center text-[#636366]">尚無入帳紀錄</td>
                        </tr>
                      ) : (
                        grantsPager.slice.map((g) => (
                          <tr key={g.grant_id} className="border-t border-white/[0.04]">
                            <td className="py-1">{POOL_LABELS_ZH[g.pool_type] ?? g.pool_type}</td>
                            <td>{g.source}</td>
                            <td className="text-[#64D2FF]">{g.origin || '—'}</td>
                            <td className="tabular-nums">{fmtCredits(g.remaining)}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                  <ConsolePagination
                    page={grantsPager.page}
                    totalPages={grantsPager.pages}
                    onPageChange={grantsPager.setPage}
                    className="!border-0"
                  />
                </ConsoleCardBody>
              </ConsoleCard>
            ) : null}

            {poolsPager.page === 3 ? (
              <ConsoleCard>
                <ConsoleCardHeader>滾存紀錄</ConsoleCardHeader>
                <ConsoleCardBody dense>
                  {rolloversPager.slice.length === 0 ? (
                    <p className="text-[11px] text-[#636366]">尚無滾存紀錄</p>
                  ) : (
                    <table className="w-full text-left text-[11px]">
                      <thead className="text-[#8E8E93]">
                        <tr>
                          <th>月份</th>
                          <th>未用</th>
                          <th>滾入</th>
                          <th>作廢</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rolloversPager.slice.map((r, i) => (
                          <tr key={i} className="border-t border-white/[0.04]">
                            <td>{String(r.month_key)}</td>
                            <td>{fmtCredits(Number(r.unused_monthly))}</td>
                            <td className="text-[#30D158]">{fmtCredits(Number(r.rolled_to_purchased))}</td>
                            <td className="text-[#FF9F9A]">{fmtCredits(Number(r.forfeited))}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  <ConsolePagination
                    page={rolloversPager.page}
                    totalPages={rolloversPager.pages}
                    onPageChange={rolloversPager.setPage}
                    className="!border-0"
                  />
                </ConsoleCardBody>
              </ConsoleCard>
            ) : null}
          </ConsoleSection>
        </ConsolePageFrame>
      ) : null}

      {section === 'contribution' && contribution ? (
        <ConsolePageFrame
          page={contributionPager.page}
          totalPages={contributionPager.pages}
          onPageChange={(p) => {
            contributionPager.setPage(p);
            if (p === 3) installmentsPager.reset();
          }}
        >
          <ConsoleSection id="credits-contribution" title="貢獻轉換" description="未鎖定轉已購買、鎖倉分期與解鎖進度">
            {contributionPager.page === 1 ? (
              <>
                <div className="rounded-lg border border-[#64D2FF]/20 bg-[#64D2FF]/5 px-3 py-2 text-[12px] text-[#AEAEB2]">
                  <p>
                    {contribution.notice_zh ??
                      lockThresholdNotice(
                        contribution.accumulated_unlocked,
                        contribution.convert_threshold,
                        contribution.convertible_to_locked,
                      )}
                  </p>
                  {contribution.threshold_dynamic ? (
                    <p className="mt-1 text-[11px] text-[#64D2FF]">閾值依方案與累積貢獻動態調整，非固定 50</p>
                  ) : null}
                </div>
                <div className="grid gap-3 lg:grid-cols-2">
                  <ConsoleCard>
                    <ConsoleCardHeader>未鎖定 → 已購買（1:0.4）</ConsoleCardHeader>
                    <ConsoleCardBody>
                      <ConvertForm
                        max={contribution.unlocked}
                        empty={contribution.unlocked <= 0}
                        preview={(a) => convertPreview(a, contribution.convert_ratio_to_purchased)}
                        onSubmit={(a) =>
                          run(
                            () => convertContribution(a),
                            `已轉換 ${fmtCredits(a)} → ${fmtCredits(convertPreview(a))} 已購買`,
                          )
                        }
                        busy={busy}
                      />
                    </ConsoleCardBody>
                  </ConsoleCard>
                  <ConsoleCard>
                    <ConsoleCardHeader>轉鎖倉（30/90/180 天）</ConsoleCardHeader>
                    <ConsoleCardBody>
                      <LockForm
                        max={contribution.convertible_to_locked}
                        empty={contribution.convertible_to_locked <= 0}
                        tiers={contribution.lock_tiers}
                        onPreviewChange={setLockPreview}
                        onSubmit={(amount, days) =>
                          run(() => lockContribution(amount, days), `已鎖倉 ${fmtCredits(amount)} · ${days} 天`)
                        }
                        busy={busy}
                      />
                    </ConsoleCardBody>
                  </ConsoleCard>
                </div>
              </>
            ) : null}

            {contributionPager.page === 2 ? (
              <ContributionCharts contribution={contribution} poolLedger={poolLedger} lockPreview={lockPreview} />
            ) : null}

            {contributionPager.page === 3 ? (
              <ConsoleCard>
                <ConsoleCardHeader>分期解鎖進度</ConsoleCardHeader>
                <ConsoleCardBody dense>
                  {installmentsPager.slice.length === 0 ? (
                    <p className="text-[11px] text-[#636366]">尚無鎖倉分期</p>
                  ) : (
                    <ul className="space-y-2 text-[11px]">
                      {installmentsPager.slice.map((ins) => (
                        <li key={ins.installment_id} className="rounded-lg bg-black/20 px-3 py-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-[#F5F5F7]">
                              {ins.lock_days} 天 ×{ins.lock_multiplier}
                            </span>
                            <span>{installmentProgress(ins.paid_installments)}</span>
                            <span>本金 {fmtCredits(ins.per_installment)}/期</span>
                            {ins.reward_remaining != null && ins.reward_remaining > 0 ? (
                              <span className="text-[#30D158]">待發獎勵 {fmtCredits(ins.reward_remaining)}</span>
                            ) : null}
                          </div>
                          <p className="mt-1 text-[#8E8E93]">
                            {ins.schedule_zh ?? installmentScheduleZh(ins.next_due_at, ins.interval_days ?? 30)}
                            {ins.status !== 'active' ? ` · ${ins.status}` : ''}
                          </p>
                          {ins.failure_reason === 'key_failure' && ins.appeal_deadline ? (
                            <p className="mt-1 text-[#FF9F9A]">{keyFailureAppealNoticeZh(ins.appeal_deadline)}</p>
                          ) : null}
                          {ins.status === 'active' ? (
                            <button
                              type="button"
                              disabled={busy}
                              className="mt-2 text-[11px] text-[#FF9F9A]"
                              onClick={() => {
                                const reward = ins.reward_remaining ?? 0;
                                const penalty = ins.total_amount * 0.05;
                                const returned = Math.max(0, (ins.principal_remaining ?? 0) - penalty);
                                const confirmMsg = earlyUnlockConfirmZh(reward, penalty, returned);
                                if (window.confirm(confirmMsg)) {
                                  void run(() => earlyUnlockContribution(ins.installment_id), '已提前解鎖');
                                }
                              }}
                            >
                              提前解鎖（沒收獎勵 + 5% 本金）
                            </button>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                  <ConsolePagination
                    page={installmentsPager.page}
                    totalPages={installmentsPager.pages}
                    onPageChange={installmentsPager.setPage}
                    className="!border-0"
                  />
                  <button
                    type="button"
                    disabled={busy}
                    className="mt-2 text-[11px] text-[#64D2FF]"
                    onClick={() => void run(() => triggerInstallments(false), '已處理到期分期')}
                  >
                    處理到期分期
                  </button>
                </ConsoleCardBody>
              </ConsoleCard>
            ) : null}
          </ConsoleSection>
        </ConsolePageFrame>
      ) : null}

      {section === 'contributor' ? (
        <ConsolePageFrame
          page={contributorPager.page}
          totalPages={contributorPager.pages}
          onPageChange={contributorPager.setPage}
        >
          <ConsoleSection
            id="credits-contributor"
            title="貢獻者"
            description="共享池 API Key 綁定與健康度（AES-256 加密代理）"
          >
            <ContributorPanel
              onMsg={setMsg}
              busy={busy}
              setBusy={setBusy}
              page={contributorPager.page}
            />
          </ConsoleSection>
        </ConsolePageFrame>
      ) : null}

      {section === 'appeals' ? (
        <ConsolePageFrame
          page={appealsPager.page}
          totalPages={appealsPager.pages}
          onPageChange={(p) => {
            appealsPager.setPage(p);
            if (p === 2) appealsListPager.reset();
          }}
        >
          <ConsoleSection id="credits-appeals" title="申訴" description="計費申訴與 Key 故障沒收申訴">
            {appealsPager.page === 1 ? (
              <ConsoleCard>
                <ConsoleCardHeader>提交申訴</ConsoleCardHeader>
                <ConsoleCardBody>
                  <AppealForm
                    forfeitedInstallments={(contribution?.installments ?? []).filter(
                      (i) => i.status === 'forfeited_key_failure' && i.appeal_deadline,
                    )}
                    onSubmit={(r, d, t, kind, installmentId) =>
                      run(() => submitBillingAppeal(r, d, t, { appealKind: kind, installmentId }), '申訴已提交')
                    }
                    busy={busy}
                  />
                </ConsoleCardBody>
              </ConsoleCard>
            ) : null}
            {appealsPager.page === 2 ? (
              <ConsoleCard>
                <ConsoleCardHeader>申訴紀錄</ConsoleCardHeader>
                <ConsoleCardBody dense>
                  {appealsListPager.slice.length === 0 ? (
                    <p className="text-[11px] text-[#636366]">尚無申訴</p>
                  ) : (
                    <ul className="space-y-2 text-[11px]">
                      {appealsListPager.slice.map((a) => (
                        <li key={a.appeal_id} className="rounded-lg border border-white/[0.06] px-3 py-2">
                          <span className="text-[#F5F5F7]">{a.reason}</span>
                          <span className="ml-2 text-[#8E8E93]">{a.status}</span>
                          {a.appeal_kind === 'key_failure_forfeiture' ? (
                            <span className="ml-2 text-[#FF9F9A]">Key 故障沒收</span>
                          ) : null}
                          <p className="text-[#636366]">{a.detail}</p>
                          {a.forfeiture_amount != null ? (
                            <p className="text-[#636366]">沒收金額 {fmtCredits(a.forfeiture_amount)}</p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                  <ConsolePagination
                    page={appealsListPager.page}
                    totalPages={appealsListPager.pages}
                    onPageChange={appealsListPager.setPage}
                    className="!border-0"
                  />
                </ConsoleCardBody>
              </ConsoleCard>
            ) : null}
          </ConsoleSection>
        </ConsolePageFrame>
      ) : null}

      {section === 'admin' ? (
        <ConsoleSection id="credits-admin" title="管理" description="定價、政策、廠商、Fault Pool 與路由（需 Admin Secret）">
          <BillingAdminPanel onMsg={setMsg} embedded />
        </ConsoleSection>
      ) : null}
    </div>
  );

  return (
    <PanelShell scroll={false}>
      <ConsoleSectionNav
        sections={NAV_ITEMS}
        activeId={creditsAnchorId(section)}
        onSelect={onNavSelect}
      />

      {msg ? (
        <div className="shrink-0 px-4 pt-2 sm:px-6">
          <PanelAlert tone="notice">{msg}</PanelAlert>
        </div>
      ) : null}

      <ConsoleTabBody>
        <SectionHeader
          title="靈境積分中心"
          description="積分帳務、Docker 按時計費、阿里雲 BSS、貢獻鎖倉與管理台 — 分頁切換，無整頁滾動"
          meta="深鏈：#/monitor/credits/pools · #/monitor/billing → 雲與 Docker"
        />
        {sectionBody}
      </ConsoleTabBody>
    </PanelShell>
  );
}

function ConvertForm({
  max,
  empty,
  preview,
  onSubmit,
  busy,
}: {
  max: number;
  empty?: boolean;
  preview: (a: number) => number;
  onSubmit: (a: number) => void;
  busy: boolean;
}) {
  const [amount, setAmount] = useState('10');
  const a = Number(amount);
  const disabled = busy || Boolean(empty) || a <= 0 || a > max;
  return (
    <div className="space-y-2">
      {empty ? (
        <p className="rounded border border-[#FFD60A]/20 bg-[#FFD60A]/5 px-2 py-1.5 text-[11px] text-[#FFD60A]">
          {CONTRIBUTION_EMPTY_ZH}
        </p>
      ) : null}
      <input
        type="number"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        disabled={empty}
        className="w-full rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px] disabled:opacity-40"
      />
      <p className="text-[10px] text-[#636366]">
        預覽入帳 {fmtCredits(preview(a))} 已購買（最多 {fmtCredits(max)}）
      </p>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onSubmit(a)}
        className="text-[12px] text-[#64D2FF] disabled:opacity-40"
      >
        轉換
      </button>
    </div>
  );
}

function LockForm({
  max,
  empty,
  tiers,
  onSubmit,
  onPreviewChange,
  busy,
}: {
  max: number;
  empty?: boolean;
  tiers: Record<string, number>;
  onSubmit: (a: number, d: number) => void;
  onPreviewChange: (p: LockPreview) => void;
  busy: boolean;
}) {
  const [amount, setAmount] = useState('10');
  const [days, setDays] = useState(30);
  const a = Number(amount);
  const mult = Number(tiers[String(days)] ?? tiers[days] ?? 1.02);
  const disabled = busy || Boolean(empty) || a <= 0 || a > max;

  const emitPreview = (amt: number, d: number) => {
    const m = Number(tiers[String(d)] ?? tiers[d] ?? 1.02);
    onPreviewChange({ amount: amt, days: d, multiplier: m });
  };

  useEffect(() => {
    emitPreview(a, days);
  }, []);

  return (
    <div className="space-y-2">
      {empty ? (
        <p className="rounded border border-[#FFD60A]/20 bg-[#FFD60A]/5 px-2 py-1.5 text-[11px] text-[#FFD60A]">
          {CONTRIBUTION_EMPTY_ZH}
        </p>
      ) : null}
      <input
        type="number"
        value={amount}
        disabled={empty}
        onChange={(e) => {
          setAmount(e.target.value);
          emitPreview(Number(e.target.value), days);
        }}
        className="w-full rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px] disabled:opacity-40"
      />
      <select
        value={days}
        disabled={empty}
        onChange={(e) => {
          const d = Number(e.target.value);
          setDays(d);
          emitPreview(a, d);
        }}
        className="w-full rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px] disabled:opacity-40"
      >
        {Object.entries(tiers).map(([d, m]) => (
          <option key={d} value={d}>
            {d} 天 · 倍率 ×{m}
          </option>
        ))}
      </select>
      <p className="text-[10px] text-[#636366]">預估獎勵 ×{mult} → +{fmtCredits(a * Math.max(0, mult - 1))}</p>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onSubmit(a, days)}
        className="text-[12px] text-[#64D2FF] disabled:opacity-40"
      >
        鎖倉
      </button>
    </div>
  );
}

function AppealForm({
  onSubmit,
  busy,
  forfeitedInstallments,
}: {
  onSubmit: (reason: string, detail: string, taskId: string, kind: string, installmentId: string) => void;
  busy: boolean;
  forfeitedInstallments: import('../../types').LockInstallment[];
}) {
  const [reason, setReason] = useState('');
  const [detail, setDetail] = useState('');
  const [taskId, setTaskId] = useState('');
  const [kind, setKind] = useState('general');
  const [installmentId, setInstallmentId] = useState('');
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]"
        >
          <option value="general">一般申訴</option>
          <option value="key_failure_forfeiture">Key 故障沒收申訴</option>
        </select>
        {kind === 'key_failure_forfeiture' ? (
          <select
            value={installmentId}
            onChange={(e) => setInstallmentId(e.target.value)}
            className="min-w-[12rem] rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]"
          >
            <option value="">選擇分期</option>
            {forfeitedInstallments.map((i) => (
              <option key={i.installment_id} value={i.installment_id}>
                {i.installment_id.slice(-8)} · 沒收 {fmtCredits(i.forfeited_amount ?? 0)}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          placeholder="申訴原因"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="flex-1 rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]"
        />
        <input
          placeholder="任務 ID（選填）"
          value={taskId}
          onChange={(e) => setTaskId(e.target.value)}
          className="w-32 rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]"
        />
        <input
          placeholder="詳情"
          value={detail}
          onChange={(e) => setDetail(e.target.value)}
          className="flex-1 rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]"
        />
        <button
          type="button"
          disabled={busy || !reason.trim() || (kind === 'key_failure_forfeiture' && !installmentId)}
          onClick={() => onSubmit(reason, detail, taskId, kind, installmentId)}
          className="text-[12px] text-[#64D2FF]"
        >
          提交
        </button>
      </div>
    </div>
  );
}

function ContributorPanel({
  onMsg,
  busy,
  setBusy,
  page = 1,
}: {
  onMsg: (m: string) => void;
  busy: boolean;
  setBusy: (b: boolean) => void;
  page?: number;
}) {
  const [earnings, setEarnings] = useState<Record<string, unknown> | null>(null);
  const [keys, setKeys] = useState<Record<string, unknown>[]>([]);
  const [keyVal, setKeyVal] = useState('');
  const [orgId, setOrgId] = useState('');
  const [dailyCap, setDailyCap] = useState('1000000');
  const [concurrency, setConcurrency] = useState('2');
  const [vendorId, setVendorId] = useState('self_host');

  const refresh = useCallback(async () => {
    const [e, k] = await Promise.all([fetchContributorEarnings(), fetchContributorKeys()]);
    setEarnings(e);
    setKeys((k.items as Record<string, unknown>[]) ?? []);
  }, []);

  useEffect(() => {
    void refresh().catch((err) => onMsg(err instanceof Error ? err.message : String(err)));
  }, [refresh, onMsg]);

  const healthColor = (status: string | undefined) => {
    if (status === 'healthy') return 'text-[#30D158]';
    if (status === 'degraded') return 'text-[#FFD60A]';
    return 'text-[#FF9F9A]';
  };

  const keysPager = usePagination(keys, 4);

  return (
    <div className="space-y-3">
      {page === 1 ? (
        <>
          <KpiGrid>
            <KpiCard label="未鎖收益" value={fmtCredits(Number(earnings?.unlocked_earnings ?? 0))} />
            <KpiCard label="鎖倉收益" value={fmtCredits(Number(earnings?.locked_earnings ?? 0))} />
            <KpiCard label="已綁 Key" value={keys.length} />
          </KpiGrid>
          <ConsoleCard>
            <ConsoleCardHeader>綁定共享池 API Key</ConsoleCardHeader>
            <ConsoleCardBody>
              <p className="mb-2 text-[11px] text-[#8E8E93]">
                綁定 Key 共享調用權（非積分）。AES-256 加密代理、零日誌；僅 self_host / resale_allowed 廠商。
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                <input
                  placeholder="API Key"
                  value={keyVal}
                  onChange={(e) => setKeyVal(e.target.value)}
                  className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[12px] sm:col-span-2"
                />
                <input
                  placeholder="組織 ID（同 org 優先）"
                  value={orgId}
                  onChange={(e) => setOrgId(e.target.value)}
                  className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[12px]"
                />
                <select
                  value={vendorId}
                  onChange={(e) => setVendorId(e.target.value)}
                  className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[12px]"
                >
                  <option value="self_host">自架</option>
                  <option value="deepseek">DeepSeek</option>
                  <option value="openai">OpenAI</option>
                </select>
                <input
                  type="number"
                  placeholder="日 Token 上限"
                  value={dailyCap}
                  onChange={(e) => setDailyCap(e.target.value)}
                  className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[12px]"
                />
                <input
                  type="number"
                  placeholder="並發"
                  value={concurrency}
                  onChange={(e) => setConcurrency(e.target.value)}
                  className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[12px]"
                />
              </div>
              <button
                type="button"
                disabled={busy || keyVal.length < 8}
                className="mt-2 text-[12px] text-[#64D2FF]"
                onClick={() => {
                  setBusy(true);
                  bindContributorKey(keyVal, {
                    vendorId,
                    orgId,
                    dailyTokenCap: Number(dailyCap) || 0,
                    concurrency: Number(concurrency) || 1,
                    tosClass: vendorId === 'self_host' ? 'self_host' : 'resale_allowed',
                    models: ['default'],
                  })
                    .then(() => {
                      onMsg('Key 已綁定（AES-256 加密）');
                      return refresh();
                    })
                    .catch((e) => onMsg(e instanceof Error ? e.message : '失敗'))
                    .finally(() => setBusy(false));
                }}
              >
                綁定 Key
              </button>
            </ConsoleCardBody>
          </ConsoleCard>
        </>
      ) : null}

      {page === 2 ? (
        <ConsoleCard>
          <ConsoleCardHeader>Key 健康度</ConsoleCardHeader>
          <ConsoleCardBody dense>
            {keysPager.slice.length === 0 ? (
              <p className="text-[11px] text-[#636366]">尚無綁定 Key</p>
            ) : (
              <ul className="space-y-2 text-[11px]">
                {keysPager.slice.map((k) => (
                  <li key={String(k.key_id)} className="rounded-lg border border-white/[0.06] px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-[#F5F5F7]">{String(k.key_id).slice(-10)}</span>
                      <span className={healthColor(String(k.health_status ?? k.status))}>
                        {String(k.health_status ?? k.status ?? 'healthy')}
                      </span>
                      <span className="text-[#636366]">分數 {Number(k.health_score ?? 1).toFixed(2)}</span>
                      <span className="text-[#636366]">今日 {Number(k.daily_usage ?? 0).toLocaleString()} tok</span>
                    </div>
                    <button
                      type="button"
                      className="mt-1 text-[10px] text-[#64D2FF]"
                      onClick={() =>
                        void fetchContributorKeyHealth(String(k.key_id)).then((h) =>
                          onMsg(`成功率 ${(Number(h.success_rate) * 100).toFixed(1)}% · 延遲 ${h.avg_latency_ms}ms`),
                        )
                      }
                    >
                      重新檢查
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <ConsolePagination
              page={keysPager.page}
              totalPages={keysPager.pages}
              onPageChange={keysPager.setPage}
              className="!border-0"
            />
          </ConsoleCardBody>
        </ConsoleCard>
      ) : null}
    </div>
  );
}
