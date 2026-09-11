/**
 * BillingPanel — 靈境積分：方案、餘額、用量、分類帳。
 */
import { useState } from 'react';
import { assignBillingPlan, topupBillingCredits } from '../api/client';
import { useWallet } from '../hooks/useWallet';

function fmtCredits(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 10_000) return `${(n / 1000).toFixed(1)}k`;
  return n.toFixed(1);
}

const EVENT_ZH: Record<string, string> = {
  llm_tokens: 'LLM Token',
  reflection_iter: '反思迭代',
  raho_role: 'RAHO 角色',
  quant_api: '量化 API',
  opc_write: 'OPC 寫入',
  opc_read: 'OPC 讀取',
  minecraft_op: 'Minecraft',
  docker_runtime: 'Docker 運行',
  integrations_recall: '整合召回',
  topup: '充值',
  plan_quota: '方案配額',
};

export default function WalletPanel() {
  const { account, ledger, usage, plans, loading, error, refresh } = useWallet(6000);
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

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-6">
      <header>
        <h2 className="text-[15px] font-semibold text-[#F5F5F7]">靈境積分 · 帳務中心</h2>
        <p className="mt-1 text-[12px] text-[#8E8E93]">
          訂閱方案 + 用量計費 + 功能包。1 積分 ≈ 1,000 baseline tokens（依模型倍率調整）。
        </p>
      </header>

      {error ? (
        <div className="rounded-lg border border-[#FF453A]/30 bg-[#FF453A]/10 px-3 py-2 text-[12px] text-[#FF9F9A]">{error}</div>
      ) : null}

      <section className="grid gap-3 lg:grid-cols-3">
        <div className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-4 lg:col-span-1">
          <p className="text-[11px] uppercase tracking-wide text-[#636366]">可用積分</p>
          <p className="mt-1 text-[28px] font-semibold tabular-nums text-[#F5F5F7]">
            {loading && !account ? '—' : fmtCredits(account?.balance_credits ?? 0)}
          </p>
          <p className="mt-1 text-[11px] text-[#8E8E93]">
            方案：{account?.plan_name_zh ?? '—'} · 本月已用 {fmtCredits(account?.monthly_used_credits ?? 0)} / {fmtCredits(account?.monthly_quota_credits ?? 0)}
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

      <section>
        <h3 className="mb-2 text-[13px] font-medium text-[#F5F5F7]">訂閱方案</h3>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {plans.map((p) => {
            const plan = p as { id: string; name_zh: string; monthly_credits: number; price_usd_month: number | null; description_zh: string };
            const active = account?.plan_id === plan.id;
            return (
              <div key={plan.id} className={`rounded-xl border p-3 ${active ? 'border-[#64D2FF]/50 bg-[#64D2FF]/5' : 'border-white/[0.08] bg-[#1C1C1E]'}`}>
                <p className="text-[13px] font-semibold text-[#F5F5F7]">{plan.name_zh}</p>
                <p className="text-[11px] text-[#8E8E93]">{plan.description_zh}</p>
                <p className="mt-1 text-[12px] tabular-nums text-[#AEAEB2]">
                  {plan.price_usd_month != null ? `$${plan.price_usd_month}/月` : '客製'} · {fmtCredits(plan.monthly_credits)} 積分
                </p>
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
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-[13px] font-medium text-[#F5F5F7]">最近用量事件</h3>
          <div className="max-h-64 overflow-auto rounded-xl border border-white/[0.08]">
            <table className="w-full text-left text-[11px]">
              <thead className="sticky top-0 bg-[#2C2C2E] text-[#8E8E93]">
                <tr><th className="px-2 py-1.5">時間</th><th className="px-2 py-1.5">類型</th><th className="px-2 py-1.5">積分</th></tr>
              </thead>
              <tbody>
                {usage.length === 0 ? (
                  <tr><td colSpan={3} className="px-2 py-4 text-center text-[#636366]">{loading ? '載入中…' : '尚無用量'}</td></tr>
                ) : usage.map((row) => (
                  <tr key={row.id} className="border-t border-white/[0.04]">
                    <td className="px-2 py-1.5 text-[#AEAEB2]">{new Date(row.created_at).toLocaleString('zh-TW')}</td>
                    <td className="px-2 py-1.5">{EVENT_ZH[row.event_type] ?? row.event_type}</td>
                    <td className="px-2 py-1.5 tabular-nums text-[#FF9F9A]">-{fmtCredits(row.credits)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <h3 className="mb-2 text-[13px] font-medium text-[#F5F5F7]">分類帳</h3>
          <div className="max-h-64 overflow-auto rounded-xl border border-white/[0.08]">
            <table className="w-full text-left text-[11px]">
              <thead className="sticky top-0 bg-[#2C2C2E] text-[#8E8E93]">
                <tr><th className="px-2 py-1.5">時間</th><th className="px-2 py-1.5">來源</th><th className="px-2 py-1.5">變動</th></tr>
              </thead>
              <tbody>
                {ledger.map((row) => (
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
        </div>
      </section>
    </div>
  );
}
