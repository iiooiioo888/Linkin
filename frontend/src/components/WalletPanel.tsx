/**
 * WalletPanel — 靈境積分：方案、餘額、用量、分類帳。
 */
import { useState } from 'react';
import { assignBillingPlan, topupBillingCredits } from '../api/client';
import { useWallet } from '../hooks/useWallet';
import { fmtCredits } from '../lib/billingUi';
import { useFixedPages, usePagination } from '../lib/pagination';
import { ConsolePageFrame, ConsolePagination } from './ui/ConsolePagination';

const EVENT_ZH: Record<string, string> = {
  llm_tokens: 'LLM Token',
  reflection_iter: '反思迭代',
  raho_role: 'RAHO 角色',
  quant_api: '量化 API',
  opc_write: 'OPC 寫入',
  opc_read: 'OPC 讀取',
  minecraft_op: 'Minecraft',
  docker_runtime: 'Docker 運行',
  docker: 'Docker 運行',
  integrations_recall: '整合召回',
  topup: '充值',
  plan_quota: '方案配額',
};

export default function WalletPanel({ embedded = false }: { embedded?: boolean }) {
  const { account, ledger, usage, plans, docker, loading, error, refresh } = useWallet(6000);
  const dockerLedger = ledger.filter((row) => row.source === 'docker' || row.reference.startsWith('docker:'));
  const dockerUsage = usage.filter((row) => row.event_type === 'docker_runtime');
  const [topupAmount, setTopupAmount] = useState('5000');
  const [topupBusy, setTopupBusy] = useState(false);
  const [topupMsg, setTopupMsg] = useState<string | null>(null);
  const [planBusy, setPlanBusy] = useState(false);

  const handleTopup = async () => {
    const amount = Number(topupAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setTopupMsg('請輸入有效積分數量');
      return;
    }
    setTopupBusy(true);
    setTopupMsg(null);
    try {
      await topupBillingCredits(amount);
      setTopupMsg(`已充值 ${fmtCredits(amount)} 靈境積分`);
      await refresh();
    } catch (err) {
      setTopupMsg(err instanceof Error ? err.message : '充值失敗');
    } finally {
      setTopupBusy(false);
    }
  };

  const handleAssignPlan = async (planId: string) => {
    setPlanBusy(true);
    try {
      await assignBillingPlan(planId);
      await refresh();
    } catch (err) {
      setTopupMsg(err instanceof Error ? err.message : '方案切換失敗');
    } finally {
      setPlanBusy(false);
    }
  };

  const embeddedPager = useFixedPages(5);
  const planPager = usePagination(plans, 3);
  const usagePager = usePagination(usage, 4);
  const ledgerPager = usePagination(ledger, 4);

  const body = (
    <div className={embedded ? 'space-y-3' : 'flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-6'}>
      {!embedded ? (
        <header>
          <h2 className="text-[15px] font-semibold text-[#F5F5F7]">靈境積分 · 帳務中心</h2>
          <p className="mt-1 text-[12px] text-[#8E8E93]">
            訂閱方案 + 用量計費 + 功能包。1 積分 ≈ 1,000 baseline tokens（依模型倍率調整）。
          </p>
        </header>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-[#FF453A]/30 bg-[#FF453A]/10 px-3 py-2 text-[12px] text-[#FF9F9A]">{error}</div>
      ) : null}

      {(!embedded || embeddedPager.page === 1) && (
      <section className="grid gap-3 lg:grid-cols-3">
        <div className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-4 lg:col-span-1">
          <p className="text-[11px] uppercase tracking-wide text-[#636366]">可用積分</p>
          <p className="mt-1 text-[28px] font-semibold tabular-nums text-[#F5F5F7]">
            {loading && !account ? '—' : fmtCredits(account?.balance_credits ?? 0)}
          </p>
          <p className="mt-1 text-[11px] text-[#8E8E93]">
            方案：{account?.plan_name_zh ?? '—'} · 月度贈送 {fmtCredits(account?.pool_balances?.monthly_grant ?? 0)} · 已購買 {fmtCredits(account?.pool_balances?.purchased ?? 0)}
          </p>
          <p className="mt-0.5 text-[10px] text-[#636366]">
            定價 v{account?.pricing_config_version ?? '—'} · 廠商偏好已套用 · 積分不可轉贈
          </p>
          {(account?.pool_balances?.contribution_unlocked ?? 0) > 0 ? (
            <p className="mt-1 text-[10px] text-[#64D2FF]">
              貢獻積分（未鎖）{fmtCredits(account?.pool_balances?.contribution_unlocked ?? 0)} · 可 1:0.4 轉已購買
            </p>
          ) : null}
          <p className="mt-1 text-[10px] text-[#636366]">
            月度贈送於每月初按比例滾入已購買池，剩餘作廢；L3 快取命中僅計 10% 費用
          </p>
          {account?.low_balance ? (
            <p className="mt-2 text-[11px] text-[#FF9F0A]">積分偏低，請升級方案或充值後繼續使用計費功能。</p>
          ) : null}
        </div>

        <div className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-4">
          <p className="text-[11px] uppercase tracking-wide text-[#636366]">充值（開發／測試）</p>
          <div className="mt-2 flex gap-2">
            <input
              type="number"
              min="1"
              value={topupAmount}
              onChange={(e) => setTopupAmount(e.target.value)}
              className="flex-1 rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-[13px] text-[#F5F5F7]"
            />
            <button
              type="button"
              disabled={topupBusy}
              onClick={() => void handleTopup()}
              className="rounded-lg bg-[#64D2FF]/20 px-3 py-1.5 text-[12px] font-medium text-[#64D2FF] hover:bg-[#64D2FF]/30 disabled:opacity-50"
            >
              {topupBusy ? '處理中…' : '充值'}
            </button>
          </div>
          {topupMsg ? <p className="mt-2 text-[11px] text-[#AEAEB2]">{topupMsg}</p> : null}
        </div>

        <div className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-4">
          <p className="text-[11px] uppercase tracking-wide text-[#636366]">功能包權益</p>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {(account?.features ?? []).map((f) => (
              <li key={f} className="rounded-md bg-[#30D158]/15 px-2 py-0.5 text-[10px] text-[#30D158]">{f}</li>
            ))}
          </ul>
        </div>
      </section>
      )}

      {(!embedded || embeddedPager.page === 2) && (
      <section>
        <h3 className="mb-2 text-[13px] font-medium text-[#F5F5F7]">訂閱方案</h3>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {(embedded ? planPager.slice : plans).map((p) => {
            const plan = p as {
              id: string;
              name_zh: string;
              monthly_credits: number;
              price_usd_month: number | null;
              description_zh: string;
              docker?: { rate_multiplier: number; included_hours_per_month: number; description_zh: string };
            };
            const active = account?.plan_id === plan.id;
            return (
              <div key={plan.id} className={`rounded-xl border p-3 ${active ? 'border-[#64D2FF]/50 bg-[#64D2FF]/5' : 'border-white/[0.08] bg-[#1C1C1E]'}`}>
                <p className="text-[13px] font-semibold text-[#F5F5F7]">{plan.name_zh}</p>
                <p className="text-[11px] text-[#8E8E93]">{plan.description_zh}</p>
                <p className="mt-1 text-[12px] tabular-nums text-[#AEAEB2]">
                  {plan.price_usd_month != null ? `$${plan.price_usd_month}/月` : '客製'} · {fmtCredits(plan.monthly_credits)} 積分
                </p>
                {plan.docker ? (
                  <p className="mt-0.5 text-[10px] text-[#636366]">{plan.docker.description_zh}</p>
                ) : null}
                {!active ? (
                  <button
                    type="button"
                    disabled={planBusy}
                    onClick={() => void handleAssignPlan(plan.id)}
                    className="mt-2 text-[11px] text-[#64D2FF] hover:underline disabled:opacity-50"
                  >
                    切換方案
                  </button>
                ) : (
                  <span className="mt-2 inline-block text-[10px] text-[#64D2FF]">目前方案</span>
                )}
              </div>
            );
          })}
        </div>
        {embedded ? (
          <ConsolePagination
            page={planPager.page}
            totalPages={planPager.pages}
            onPageChange={planPager.setPage}
            className="!border-0"
          />
        ) : null}
      </section>
      )}

      {(!embedded || embeddedPager.page === 3) && (
      <section className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-4">
        <h3 className="mb-2 text-[13px] font-medium text-[#F5F5F7]">Docker 即時計費</h3>
        <p className="text-[11px] text-[#8E8E93]">
          依目前方案「{docker?.plan_terms?.plan_name_zh ?? account?.plan_name_zh ?? '—'}」套用 Docker 費率倍率
          ×{docker?.plan_terms?.rate_multiplier ?? '—'}；含額 {docker?.plan_terms?.included_hours_per_month ?? 0} h/月
          （已用 {docker?.plan_terms?.included_hours_used?.toFixed(1) ?? '0'} h · 剩餘 {docker?.plan_terms?.included_hours_remaining?.toFixed(1) ?? '0'} h）。
          每 {docker?.tick_interval_sec ?? 30} 秒結算至積分。
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-lg bg-black/20 px-3 py-2">
            <p className="text-[10px] text-[#636366]">方案 Docker 牌價時費</p>
            <p className="text-[14px] tabular-nums text-[#F5F5F7]">{fmtCredits(docker?.projected_hourly_credits ?? 0)} 積分/h</p>
          </div>
          <div className="rounded-lg bg-black/20 px-3 py-2">
            <p className="text-[10px] text-[#636366]">超額預估時費</p>
            <p className="text-[14px] tabular-nums text-[#F5F5F7]">
              {fmtCredits(docker?.projected_billable_hourly_credits ?? docker?.projected_hourly_credits ?? 0)} 積分/h
            </p>
          </div>
          <div className="rounded-lg bg-black/20 px-3 py-2">
            <p className="text-[10px] text-[#636366]">已扣 Docker 積分</p>
            <p className="text-[14px] tabular-nums text-[#FF9F9A]">{fmtCredits(docker?.total_docker_credits_spent ?? 0)}</p>
          </div>
          <div className="rounded-lg bg-black/20 px-3 py-2">
            <p className="text-[10px] text-[#636366]">我的運行中服務</p>
            <p className="text-[14px] text-[#F5F5F7]">
              {docker?.running_services?.filter((s) => s.is_mine).length ?? 0} 個
            </p>
          </div>
        </div>
        {(docker?.running_services?.filter((s) => s.is_mine).length ?? 0) > 0 ? (
          <ul className="mt-3 space-y-1 text-[11px] text-[#AEAEB2]">
            {docker?.running_services?.filter((s) => s.is_mine).map((svc) => (
              <li key={svc.service} className="flex justify-between gap-2">
                <span>
                  {svc.service}
                  {svc.is_core ? '（核心）' : ''}
                  {svc.rate_multiplier != null && svc.rate_multiplier !== 1 ? ` · ×${svc.rate_multiplier}` : ''}
                </span>
                <span className="tabular-nums">{fmtCredits(svc.credits_per_hour)}/h · {svc.uptime_hours.toFixed(2)}h</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-[11px] text-[#48484A]">目前無您名下的計費運行容器（或 Docker 不可用）</p>
        )}
        {dockerUsage.length > 0 ? (
          <p className="mt-2 text-[10px] text-[#636366]">最近 Docker 用量事件 {dockerUsage.length} 筆 · 分類帳 Docker 行 {dockerLedger.length} 筆</p>
        ) : null}
      </section>
      )}

      {(!embedded || embeddedPager.page === 4) && (
        <section>
          <h3 className="mb-2 text-[13px] font-medium text-[#F5F5F7]">最近用量事件</h3>
          <div className="rounded-xl border border-white/[0.08]">
            <table className="w-full text-left text-[11px]">
              <thead className="bg-[#2C2C2E] text-[#8E8E93]">
                <tr><th className="px-2 py-1.5">時間</th><th className="px-2 py-1.5">類型</th><th className="px-2 py-1.5">積分</th></tr>
              </thead>
              <tbody>
                {(embedded ? usagePager.slice : usage).length === 0 ? (
                  <tr><td colSpan={3} className="px-2 py-4 text-center text-[#636366]">{loading ? '載入中…' : '尚無用量'}</td></tr>
                ) : (embedded ? usagePager.slice : usage).map((row) => (
                  <tr key={row.id} className="border-t border-white/[0.04]">
                    <td className="px-2 py-1.5 text-[#AEAEB2]">{new Date(row.created_at).toLocaleString('zh-TW')}</td>
                    <td className="px-2 py-1.5">{EVENT_ZH[row.event_type] ?? row.event_type}</td>
                    <td className="px-2 py-1.5 tabular-nums text-[#FF9F9A]">-{fmtCredits(row.credits)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {embedded ? (
            <ConsolePagination
              page={usagePager.page}
              totalPages={usagePager.pages}
              onPageChange={usagePager.setPage}
              className="!border-0"
            />
          ) : null}
        </section>
      )}

      {(!embedded || embeddedPager.page === 5) && (
        <section>
          <h3 className="mb-2 text-[13px] font-medium text-[#F5F5F7]">分類帳</h3>
          <div className="rounded-xl border border-white/[0.08]">
            <table className="w-full text-left text-[11px]">
              <thead className="bg-[#2C2C2E] text-[#8E8E93]">
                <tr><th className="px-2 py-1.5">時間</th><th className="px-2 py-1.5">來源</th><th className="px-2 py-1.5">變動</th></tr>
              </thead>
              <tbody>
                {(embedded ? ledgerPager.slice : ledger).map((row) => (
                  <tr key={row.id} className="border-t border-white/[0.04]">
                    <td className="px-2 py-1.5 text-[#AEAEB2]">{new Date(row.created_at).toLocaleString('zh-TW')}</td>
                    <td className="px-2 py-1.5">{EVENT_ZH[row.source] ?? row.source}</td>
                    <td className={`px-2 py-1.5 tabular-nums ${row.amount_credits < 0 ? 'text-[#FF9F9A]' : 'text-[#30D158]'}`}>
                      {row.amount_credits > 0 ? '+' : ''}{fmtCredits(row.amount_credits)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {embedded ? (
            <ConsolePagination
              page={ledgerPager.page}
              totalPages={ledgerPager.pages}
              onPageChange={ledgerPager.setPage}
              className="!border-0"
            />
          ) : null}
        </section>
      )}
    </div>
  );

  if (embedded) {
    const onPageChange = (p: number) => {
      embeddedPager.setPage(p);
      if (p === 2) planPager.reset();
      if (p === 4) usagePager.reset();
      if (p === 5) ledgerPager.reset();
    };
    return (
      <ConsolePageFrame page={embeddedPager.page} totalPages={embeddedPager.pages} onPageChange={onPageChange}>
        {body}
      </ConsolePageFrame>
    );
  }

  return body;
}
