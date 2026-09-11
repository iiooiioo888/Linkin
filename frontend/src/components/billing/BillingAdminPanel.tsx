/**
 * 計費管理台 — 定價 / 政策 / 廠商 / 滾存 / 申訴 / fault_pool / cache / 路由
 */
import { useCallback, useEffect, useState } from 'react';
import {
  adminActivateCreditPolicy,
  adminActivatePricing,
  adminActivateVendor,
  adminListAppeals,
  adminListCreditPolicies,
  adminListPricingConfigs,
  adminListVendorConfigs,
  adminResolveAppeal,
  adminRunRollover,
  adminGetCacheStats,
  adminGetFaultPool,
  adminGetRoutingStats,
  adminResumePublicPool,
  adminSeedContribution,
  adminGetTaskLedger,
} from '../../api/client';
import { fmtCredits } from '../../lib/billingUi';

const ADMIN_KEY_STORAGE = 'linkin_billing_admin_secret';

type FaultPoolView = {
  balance?: number;
  total?: number;
  depleted?: boolean;
  public_pool_paused?: boolean;
  platform_take_rate?: number;
  notice_zh?: string;
  alerts?: { message_zh: string; created_at: string }[];
  ledger_recent?: { entry_type: string; amount: number; reason: string; balance_after: number }[];
  by_reason?: { reason: string; entry_type: string; total: number }[];
};

export default function BillingAdminPanel({
  onMsg,
  embedded = false,
}: {
  onMsg: (m: string) => void;
  embedded?: boolean;
}) {
  const [secret, setSecret] = useState(() => localStorage.getItem(ADMIN_KEY_STORAGE) ?? '');
  const [pricing, setPricing] = useState<Record<string, unknown>[]>([]);
  const [policies, setPolicies] = useState<Record<string, unknown>[]>([]);
  const [vendors, setVendors] = useState<Record<string, unknown>>({});
  const [appeals, setAppeals] = useState<Record<string, unknown>[]>([]);
  const [fault, setFault] = useState<FaultPoolView | null>(null);
  const [routing, setRouting] = useState<Record<string, unknown> | null>(null);
  const [cache, setCache] = useState<Record<string, unknown> | null>(null);
  const [taskId, setTaskId] = useState('');
  const [ledger, setLedger] = useState<Record<string, unknown> | null>(null);
  const [seedAccount, setSeedAccount] = useState('');
  const [seedAmount, setSeedAmount] = useState('100');

  const headers = () => ({ 'X-Billing-Admin': secret });

  const load = useCallback(async () => {
    if (!secret) return;
    try {
      const [p, pol, v, a, f, r, c] = await Promise.all([
        adminListPricingConfigs(headers()),
        adminListCreditPolicies(headers()),
        adminListVendorConfigs(headers()),
        adminListAppeals(headers()),
        adminGetFaultPool(headers()),
        adminGetRoutingStats(headers()),
        adminGetCacheStats(headers()),
      ]);
      setPricing(p.items ?? []);
      setPolicies(pol.items ?? []);
      setVendors(v);
      setAppeals(a.items ?? []);
      setFault(f as FaultPoolView);
      setRouting(r);
      setCache(c);
    } catch (err) {
      onMsg(err instanceof Error ? err.message : '管理台載入失敗');
    }
  }, [secret, onMsg]);

  useEffect(() => {
    localStorage.setItem(ADMIN_KEY_STORAGE, secret);
    void load();
  }, [load, secret]);

  const faultBalance = Number(fault?.balance ?? fault?.total ?? 0);

  return (
    <div className={embedded ? 'space-y-3' : 'space-y-4 p-6'}>
      {!embedded ? (
        <header>
          <h2 className="text-[15px] font-semibold text-[#F5F5F7]">計費管理台</h2>
          <p className="mt-1 text-[11px] text-[#8E8E93]">需 Admin Secret（開發環境可留空使用 Gate 用戶）</p>
        </header>
      ) : null}
      <input
        type="password"
        placeholder="X-Billing-Admin"
        value={secret}
        onChange={(e) => setSecret(e.target.value)}
        className="max-w-md rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[12px]"
      />

      <section className="grid gap-3 lg:grid-cols-2">
        <AdminList title="定價配置" items={pricing} onActivate={(v) => adminActivatePricing(v, headers()).then(() => load())} versionKey="version" />
        <AdminList title="積分政策" items={policies} onActivate={(v) => adminActivateCreditPolicy(v, headers()).then(() => load())} versionKey="version" />
      </section>

      <section className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-4">
        <h3 className="text-[13px] font-medium text-[#F5F5F7]">廠商配置 · 路由權重 标准/优选/战略</h3>
        <p className="text-[11px] text-[#8E8E93]">活躍版本 v{(vendors.active as { version?: number })?.version ?? '—'}</p>
        <ul className="mt-2 text-[11px]">
          {((vendors.items as Record<string, unknown>[]) ?? []).map((row) => (
            <li key={String(row.version)} className="flex justify-between gap-2 py-1">
              <span>v{String(row.version)} · {String(row.status)}</span>
              {row.status === 'draft' ? (
                <button type="button" className="text-[#64D2FF]" onClick={() => void adminActivateVendor(Number(row.version), headers()).then(() => load())}>啟用</button>
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-[13px] font-medium text-[#F5F5F7]">Fault Pool 運行時</h3>
            <p className="mt-1 text-[11px] text-[#8E8E93]">{fault?.notice_zh ?? '獨立分類帳 · 鎖倉獎勵／沒收資金池'}</p>
          </div>
          {fault?.public_pool_paused ? (
            <button
              type="button"
              className="rounded border border-[#FF9F9A]/40 px-2 py-1 text-[11px] text-[#FF9F9A]"
              onClick={() => void adminResumePublicPool(headers()).then(() => { onMsg('公共池已恢復'); void load(); })}
            >
              恢復公共池
            </button>
          ) : null}
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-4">
          <Stat label="餘額" value={fmtCredits(faultBalance)} highlight={fault?.depleted} />
          <Stat label="平台抽成" value={`${(((fault?.platform_take_rate ?? routing?.platform_take_rate ?? 0.08) as number) * 100).toFixed(1)}%`} />
          <Stat label="公共池" value={fault?.public_pool_paused ? '已暫停' : '運行中'} warn={fault?.public_pool_paused} />
          <Stat label="快取節省" value={fmtCredits(Number(cache?.savings_credits ?? 0))} />
        </div>
        {(fault?.alerts ?? []).length > 0 ? (
          <ul className="mt-2 space-y-1 text-[10px] text-[#FF9F9A]">
            {fault!.alerts!.slice(0, 3).map((a, i) => (
              <li key={i}>{a.message_zh}</li>
            ))}
          </ul>
        ) : null}
        {(fault?.ledger_recent ?? []).length > 0 ? (
          <table className="mt-3 w-full text-left text-[10px]">
            <thead className="text-[#636366]"><tr><th>類型</th><th>原因</th><th>金額</th><th>餘額</th></tr></thead>
            <tbody>
              {fault!.ledger_recent!.slice(0, 5).map((row, i) => (
                <tr key={i} className="border-t border-white/[0.04]">
                  <td>{row.entry_type}</td>
                  <td>{row.reason}</td>
                  <td className="tabular-nums">{fmtCredits(row.amount)}</td>
                  <td className="tabular-nums">{fmtCredits(row.balance_after)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </section>

      <section className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-4">
        <h3 className="text-[13px] font-medium text-[#F5F5F7]">路由決策統計</h3>
        <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
          {((routing?.by_mode as { routing_mode: string; c: number }[]) ?? []).map((m) => (
            <span key={m.routing_mode} className="rounded bg-black/30 px-2 py-1">
              {m.routing_mode} · {m.c}
            </span>
          ))}
        </div>
        <ul className="mt-2 max-h-32 overflow-auto text-[10px] text-[#AEAEB2]">
          {((routing?.recent as { task_id: string; routing_mode: string; created_at: string }[]) ?? []).map((r) => (
            <li key={r.task_id + r.created_at} className="border-t border-white/[0.04] py-1">
              {r.task_id.slice(-12)} · {r.routing_mode} · {r.created_at.slice(0, 19)}
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-4">
        <h3 className="text-[13px] font-medium text-[#F5F5F7]">Dev · 注入貢獻積分</h3>
        <p className="mt-1 text-[11px] text-[#8E8E93]">共享池上線前測試 lock/convert 用（contribution_unlocked）</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <input value={seedAccount} onChange={(e) => setSeedAccount(e.target.value)} placeholder="account_id / user_id" className="min-w-[10rem] flex-1 rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]" />
          <input value={seedAmount} onChange={(e) => setSeedAmount(e.target.value)} placeholder="amount" className="w-24 rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]" />
          <button
            type="button"
            className="text-[12px] text-[#64D2FF]"
            onClick={() => {
              if (!seedAccount.trim()) return;
              void adminSeedContribution(seedAccount.trim(), Number(seedAmount) || 100, 'admin panel seed', headers())
                .then((r) => onMsg(`已注入 ${fmtCredits(Number(r.contribution_unlocked))} 貢獻積分`))
                .catch((e) => onMsg(e instanceof Error ? e.message : '注入失敗'));
            }}
          >
            注入
          </button>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-3">
        <button type="button" className="rounded-xl border border-[#64D2FF]/30 px-3 py-2 text-[12px] text-[#64D2FF]" onClick={() => void adminRunRollover(headers()).then(() => onMsg('滾存已執行'))}>
          執行月末滾存
        </button>
        <button type="button" className="rounded-xl border border-white/10 px-3 py-2 text-[12px] text-[#AEAEB2]" onClick={() => void load()}>
          重新整理
        </button>
      </section>

      <section>
        <h3 className="mb-2 text-[13px] font-medium text-[#F5F5F7]">申訴處理</h3>
        <ul className="space-y-1 text-[11px]">
          {appeals.map((a) => (
            <li key={String(a.appeal_id)} className="flex items-center justify-between rounded bg-black/20 px-2 py-1">
              <span>{String(a.reason)} · {String(a.status)}</span>
              {a.status === 'pending' ? (
                <button type="button" className="text-[#30D158]" onClick={() => void adminResolveAppeal(String(a.appeal_id), headers()).then(() => load())}>解決</button>
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="mb-2 text-[13px] font-medium text-[#F5F5F7]">任務分類帳 · 路由</h3>
        <div className="flex gap-2">
          <input value={taskId} onChange={(e) => setTaskId(e.target.value)} placeholder="task_id" className="flex-1 rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]" />
          <button type="button" className="text-[12px] text-[#64D2FF]" onClick={() => void adminGetTaskLedger(taskId, headers()).then(setLedger)}>查詢</button>
        </div>
        {ledger ? (
          <div className="mt-2 space-y-2">
            {(ledger.routing as Record<string, unknown> | null) ? (
              <p className="text-[11px] text-[#64D2FF]">
                路由 {String((ledger.routing as Record<string, unknown>).routing_mode)} · Key {String((ledger.routing as Record<string, unknown>).primary_key_id ?? '—')}
              </p>
            ) : null}
            <pre className="max-h-48 overflow-auto rounded bg-black/40 p-2 text-[10px]">{JSON.stringify(ledger, null, 2)}</pre>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function Stat({ label, value, highlight, warn }: { label: string; value: string; highlight?: boolean; warn?: boolean }) {
  return (
    <div className={`rounded-lg border p-2 ${warn ? 'border-[#FF9F9A]/30' : highlight ? 'border-[#FF9F9A]/20' : 'border-white/[0.06]'}`}>
      <p className="text-[10px] text-[#636366]">{label}</p>
      <p className={`text-[14px] tabular-nums ${warn ? 'text-[#FF9F9A]' : 'text-[#F5F5F7]'}`}>{value}</p>
    </div>
  );
}

function AdminList({
  title,
  items,
  onActivate,
  versionKey,
}: {
  title: string;
  items: Record<string, unknown>[];
  onActivate: (version: number) => Promise<unknown>;
  versionKey: string;
}) {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-4">
      <h3 className="text-[13px] font-medium text-[#F5F5F7]">{title}</h3>
      <ul className="mt-2 max-h-40 overflow-auto text-[11px]">
        {items.map((row) => (
          <li key={String(row[versionKey])} className="flex justify-between gap-2 border-t border-white/[0.04] py-1">
            <span>v{String(row[versionKey])} · {String(row.status)}</span>
            {row.status !== 'active' ? (
              <button type="button" className="text-[#64D2FF]" onClick={() => void onActivate(Number(row[versionKey]))}>啟用</button>
            ) : (
              <span className="text-[#30D158]">使用中</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
