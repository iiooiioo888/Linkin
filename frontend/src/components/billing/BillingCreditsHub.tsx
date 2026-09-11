/**
 * 靈境積分中心 — 分頁：帳務池 / 貢獻 / 貢獻者 / 申訴 / 管理
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
} from '../../lib/billingUi';
import type { BillingAppeal, BillingGrant, BillingPoolsDetail, ContributionStatus, PoolLedgerEntry } from '../../types';
import WalletPanel from '../WalletPanel';
import BillingAdminPanel from './BillingAdminPanel';
import ContributionCharts, { type LockPreview } from './ContributionCharts';

type SubTab = 'wallet' | 'pools' | 'contribution' | 'contributor' | 'appeals' | 'admin';

const TABS: { key: SubTab; label: string }[] = [
  { key: 'wallet', label: '總覽' },
  { key: 'pools', label: '積分池' },
  { key: 'contribution', label: '貢獻轉換' },
  { key: 'contributor', label: '貢獻者' },
  { key: 'appeals', label: '申訴' },
  { key: 'admin', label: '管理' },
];

export default function BillingCreditsHub() {
  const [sub, setSub] = useState<SubTab>('wallet');
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
  }, [refresh, sub]);

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

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <nav className="flex shrink-0 gap-1 border-b border-white/[0.06] bg-[#1C1C1E]/90 px-4 py-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setSub(t.key)}
            className={`rounded-lg px-3 py-1.5 text-[12px] ${sub === t.key ? 'bg-[#64D2FF]/20 text-[#64D2FF]' : 'text-[#8E8E93] hover:text-[#F5F5F7]'}`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {msg ? (
        <div className="shrink-0 mx-4 mt-2 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-[11px] text-[#AEAEB2]">{msg}</div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto">
        {sub === 'wallet' ? <WalletPanel /> : null}

        {sub === 'pools' ? (
          <div className="space-y-4 p-6">
            <header>
              <h2 className="text-[15px] font-semibold text-[#F5F5F7]">積分池明細</h2>
              <p className="mt-1 text-[12px] text-[#8E8E93]">
                {pools?.rollover_notice_zh ?? rolloverNoticeZh(0.5, 50000)}
              </p>
            </header>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(pools?.balances ?? {}).map(([k, v]) => (
                <div key={k} className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
                  <p className="text-[10px] text-[#636366]">{POOL_LABELS_ZH[k] ?? k}</p>
                  <p className="text-[18px] font-semibold tabular-nums text-[#F5F5F7]">{fmtCredits(v)}</p>
                </div>
              ))}
            </div>
            {pools?.cache_stats ? (
              <p className="text-[11px] text-[#64D2FF]">
                L3 快取累計節省 {fmtCredits(pools.cache_stats.savings_credits)} 積分 · 命中 {pools.cache_stats.l3_hits} 次
              </p>
            ) : null}
            <section>
              <h3 className="mb-2 text-[13px] font-medium text-[#F5F5F7]">入帳來源（origin）</h3>
              <table className="w-full text-left text-[11px]">
                <thead className="text-[#8E8E93]"><tr><th className="py-1">池</th><th>來源</th><th>origin</th><th>餘額</th></tr></thead>
                <tbody>
                  {grants.map((g) => (
                    <tr key={g.grant_id} className="border-t border-white/[0.04]">
                      <td className="py-1">{POOL_LABELS_ZH[g.pool_type] ?? g.pool_type}</td>
                      <td>{g.source}</td>
                      <td className="text-[#64D2FF]">{g.origin || '—'}</td>
                      <td className="tabular-nums">{fmtCredits(g.remaining)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
            <section>
              <h3 className="mb-2 text-[13px] font-medium text-[#F5F5F7]">滾存紀錄</h3>
              {rollovers.length === 0 ? (
                <p className="text-[11px] text-[#636366]">尚無滾存紀錄</p>
              ) : (
                <table className="w-full text-left text-[11px]">
                  <thead className="text-[#8E8E93]"><tr><th>月份</th><th>未用</th><th>滾入</th><th>作廢</th></tr></thead>
                  <tbody>
                    {rollovers.map((r, i) => (
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
            </section>
          </div>
        ) : null}

        {sub === 'contribution' && contribution ? (
          <div className="space-y-4 p-6">
            <h2 className="text-[15px] font-semibold text-[#F5F5F7]">貢獻積分 · 鎖倉與轉換</h2>
            <div className="rounded-lg border border-[#64D2FF]/20 bg-[#64D2FF]/5 px-3 py-2 text-[12px] text-[#AEAEB2]">
              <p>{contribution.notice_zh ?? lockThresholdNotice(contribution.accumulated_unlocked, contribution.convert_threshold, contribution.convertible_to_locked)}</p>
              {contribution.threshold_dynamic ? (
                <p className="mt-1 text-[11px] text-[#64D2FF]">閾值依方案與累積貢獻動態調整，非固定 50</p>
              ) : null}
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-4">
                <p className="text-[11px] text-[#636366]">未鎖定 → 已購買（1:0.4）</p>
                <ConvertForm
                  max={contribution.unlocked}
                  preview={(a) => convertPreview(a, contribution.convert_ratio_to_purchased)}
                  onSubmit={(a) => run(() => convertContribution(a), `已轉換 ${fmtCredits(a)} → ${fmtCredits(convertPreview(a))} 已購買`)}
                  busy={busy}
                />
              </div>
              <div className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-4">
                <p className="text-[11px] text-[#636366]">轉鎖倉（30/90/180 天）</p>
                <LockForm
                  max={contribution.convertible_to_locked}
                  tiers={contribution.lock_tiers}
                  onPreviewChange={setLockPreview}
                  onSubmit={(amount, days) => run(() => lockContribution(amount, days), `已鎖倉 ${fmtCredits(amount)} · ${days} 天`)}
                  busy={busy}
                />
              </div>
            </div>
            <ContributionCharts
              contribution={contribution}
              poolLedger={poolLedger}
              lockPreview={lockPreview}
            />
            <section>
              <h3 className="mb-2 text-[13px] font-medium text-[#F5F5F7]">分期解鎖進度</h3>
              {(contribution.installments ?? []).length === 0 ? (
                <p className="text-[11px] text-[#636366]">尚無鎖倉分期</p>
              ) : (
                <ul className="space-y-2 text-[11px]">
                  {contribution.installments!.map((ins) => (
                    <li key={ins.installment_id} className="rounded-lg bg-black/20 px-3 py-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[#F5F5F7]">{ins.lock_days} 天 ×{ins.lock_multiplier}</span>
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
                            const msg = earlyUnlockConfirmZh(reward, penalty, returned);
                            if (window.confirm(msg)) {
                              void run(
                                () => earlyUnlockContribution(ins.installment_id),
                                '已提前解鎖',
                              );
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
              <button type="button" disabled={busy} className="mt-2 text-[11px] text-[#64D2FF]" onClick={() => void run(() => triggerInstallments(false), '已處理到期分期')}>
                處理到期分期
              </button>
            </section>
          </div>
        ) : null}

        {sub === 'contributor' ? <ContributorPanel onMsg={setMsg} busy={busy} setBusy={setBusy} /> : null}

        {sub === 'appeals' ? (
          <div className="space-y-4 p-6">
            <h2 className="text-[15px] font-semibold text-[#F5F5F7]">計費申訴</h2>
            <AppealForm
              forfeitedInstallments={(contribution?.installments ?? []).filter(
                (i) => i.status === 'forfeited_key_failure' && i.appeal_deadline,
              )}
              onSubmit={(r, d, t, kind, installmentId) =>
                run(
                  () => submitBillingAppeal(r, d, t, { appealKind: kind, installmentId }),
                  '申訴已提交',
                )
              }
              busy={busy}
            />
            <ul className="space-y-2 text-[11px]">
              {appeals.map((a) => (
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
          </div>
        ) : null}

        {sub === 'admin' ? <BillingAdminPanel onMsg={setMsg} /> : null}
      </div>
    </div>
  );
}

function ConvertForm({ max, preview, onSubmit, busy }: { max: number; preview: (a: number) => number; onSubmit: (a: number) => void; busy: boolean }) {
  const [amount, setAmount] = useState('10');
  const a = Number(amount);
  return (
    <div className="mt-2 space-y-2">
      <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} className="w-full rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]" />
      <p className="text-[10px] text-[#636366]">預覽入帳 {fmtCredits(preview(a))} 已購買（最多 {fmtCredits(max)}）</p>
      <button type="button" disabled={busy || a <= 0 || a > max} onClick={() => onSubmit(a)} className="text-[12px] text-[#64D2FF]">轉換</button>
    </div>
  );
}

function LockForm({
  max,
  tiers,
  onSubmit,
  onPreviewChange,
  busy,
}: {
  max: number;
  tiers: Record<string, number>;
  onSubmit: (a: number, d: number) => void;
  onPreviewChange: (p: LockPreview) => void;
  busy: boolean;
}) {
  const [amount, setAmount] = useState('10');
  const [days, setDays] = useState(30);
  const a = Number(amount);
  const mult = Number(tiers[String(days)] ?? tiers[days] ?? 1.02);

  const emitPreview = (amt: number, d: number) => {
    const m = Number(tiers[String(d)] ?? tiers[d] ?? 1.02);
    onPreviewChange({ amount: amt, days: d, multiplier: m });
  };

  useEffect(() => {
    emitPreview(a, days);
  }, []);

  return (
    <div className="mt-2 space-y-2">
      <input
        type="number"
        value={amount}
        onChange={(e) => {
          setAmount(e.target.value);
          emitPreview(Number(e.target.value), days);
        }}
        className="w-full rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]"
      />
      <select
        value={days}
        onChange={(e) => {
          const d = Number(e.target.value);
          setDays(d);
          emitPreview(a, d);
        }}
        className="w-full rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]"
      >
        {Object.entries(tiers).map(([d, m]) => (
          <option key={d} value={d}>{d} 天 · 倍率 ×{m}</option>
        ))}
      </select>
      <p className="text-[10px] text-[#636366]">預估獎勵 ×{mult} → +{fmtCredits(a * Math.max(0, mult - 1))}</p>
      <button type="button" disabled={busy || a <= 0 || a > max} onClick={() => onSubmit(a, days)} className="text-[12px] text-[#64D2FF]">鎖倉</button>
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
        <select value={kind} onChange={(e) => setKind(e.target.value)} className="rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]">
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
        <input placeholder="申訴原因" value={reason} onChange={(e) => setReason(e.target.value)} className="flex-1 rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]" />
        <input placeholder="任務 ID（選填）" value={taskId} onChange={(e) => setTaskId(e.target.value)} className="w-32 rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]" />
        <input placeholder="詳情" value={detail} onChange={(e) => setDetail(e.target.value)} className="flex-1 rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]" />
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

function ContributorPanel({ onMsg, busy, setBusy }: { onMsg: (m: string) => void; busy: boolean; setBusy: (b: boolean) => void }) {
  const [earnings, setEarnings] = useState<Record<string, unknown> | null>(null);
  const [keyVal, setKeyVal] = useState('');

  useEffect(() => {
    void fetchContributorEarnings().then(setEarnings).catch((e) => onMsg(String(e)));
  }, [onMsg]);

  return (
    <div className="space-y-4 p-6">
      <h2 className="text-[15px] font-semibold text-[#F5F5F7]">貢獻者 · API Key</h2>
      <p className="text-[12px] text-[#8E8E93]">綁定 Key 共享調用權（非積分）。平台加密代理，收益進貢獻池。</p>
      <div className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-4">
        <p className="text-[11px] text-[#636366]">未鎖收益 {fmtCredits(Number(earnings?.unlocked_earnings ?? 0))} · 鎖倉 {fmtCredits(Number(earnings?.locked_earnings ?? 0))}</p>
        <input placeholder="加密 Key（開發用明文佔位）" value={keyVal} onChange={(e) => setKeyVal(e.target.value)} className="mt-2 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[12px]" />
        <button
          type="button"
          disabled={busy || keyVal.length < 8}
          className="mt-2 text-[12px] text-[#64D2FF]"
          onClick={() => {
            setBusy(true);
            bindContributorKey(keyVal)
              .then(() => onMsg('Key 已綁定'))
              .catch((e) => onMsg(e instanceof Error ? e.message : '失敗'))
              .finally(() => setBusy(false));
          }}
        >
          綁定 Key
        </button>
      </div>
      <ul className="text-[11px] text-[#AEAEB2]">
        {(earnings?.keys as { key_id: string; status: string }[] | undefined)?.map((k) => (
          <li key={k.key_id}>{k.key_id} · {k.status}</li>
        ))}
      </ul>
    </div>
  );
}
