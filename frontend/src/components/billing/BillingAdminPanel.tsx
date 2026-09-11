/**
 * 計費管理台 — 定價 / 政策 / 廠商 / 滾存 / 申訴 / fault_pool / cache
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
  adminGetTaskLedger,
} from '../../api/client';
import { fmtCredits } from '../../lib/billingUi';

const ADMIN_KEY_STORAGE = 'linkin_billing_admin_secret';

export default function BillingAdminPanel({ onMsg }: { onMsg: (m: string) => void }) {
  const [secret, setSecret] = useState(() => localStorage.getItem(ADMIN_KEY_STORAGE) ?? '');
  const [pricing, setPricing] = useState<Record<string, unknown>[]>([]);
  const [policies, setPolicies] = useState<Record<string, unknown>[]>([]);
  const [vendors, setVendors] = useState<Record<string, unknown>>({});
  const [appeals, setAppeals] = useState<Record<string, unknown>[]>([]);
  const [fault, setFault] = useState<Record<string, unknown> | null>(null);
  const [cache, setCache] = useState<Record<string, unknown> | null>(null);
  const [taskId, setTaskId] = useState('');
  const [ledger, setLedger] = useState<Record<string, unknown> | null>(null);

  const headers = () => ({ 'X-Billing-Admin': secret });

  const load = useCallback(async () => {
    if (!secret) return;
    try {
      const [p, pol, v, a, f, c] = await Promise.all([
        adminListPricingConfigs(headers()),
        adminListCreditPolicies(headers()),
        adminListVendorConfigs(headers()),
        adminListAppeals(headers()),
        adminGetFaultPool(headers()),
        adminGetCacheStats(headers()),
      ]);
      setPricing(p.items ?? []);
      setPolicies(pol.items ?? []);
      setVendors(v);
      setAppeals(a.items ?? []);
      setFault(f);
      setCache(c);
    } catch (err) {
      onMsg(err instanceof Error ? err.message : '管理台載入失敗');
    }
  }, [secret, onMsg]);

  useEffect(() => {
    localStorage.setItem(ADMIN_KEY_STORAGE, secret);
    void load();
  }, [load, secret]);

  return (
    <div className="space-y-4 p-6">
      <header>
        <h2 className="text-[15px] font-semibold text-[#F5F5F7]">計費管理台</h2>
        <p className="mt-1 text-[11px] text-[#8E8E93]">需 Admin Secret（開發環境可留空使用 Gate 用戶）</p>
      </header>
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
        <h3 className="text-[13px] font-medium text-[#F5F5F7]">廠商配置</h3>
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

      <section className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
          <p className="text-[10px] text-[#636366]">Fault Pool</p>
          <p className="text-[16px] tabular-nums">{fmtCredits(Number(fault?.total ?? 0))}</p>
        </div>
        <div className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
          <p className="text-[10px] text-[#636366]">快取節省</p>
          <p className="text-[16px] tabular-nums">{fmtCredits(Number(cache?.savings_credits ?? 0))}</p>
        </div>
        <button type="button" className="rounded-xl border border-[#64D2FF]/30 px-3 py-2 text-[12px] text-[#64D2FF]" onClick={() => void adminRunRollover(headers()).then(() => onMsg('滾存已執行'))}>
          執行月末滾存
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
        <h3 className="mb-2 text-[13px] font-medium text-[#F5F5F7]">任務分類帳</h3>
        <div className="flex gap-2">
          <input value={taskId} onChange={(e) => setTaskId(e.target.value)} placeholder="task_id" className="flex-1 rounded border border-white/10 bg-black/30 px-2 py-1 text-[12px]" />
          <button type="button" className="text-[12px] text-[#64D2FF]" onClick={() => void adminGetTaskLedger(taskId, headers()).then(setLedger)}>查詢</button>
        </div>
        {ledger ? <pre className="mt-2 max-h-48 overflow-auto rounded bg-black/40 p-2 text-[10px]">{JSON.stringify(ledger, null, 2)}</pre> : null}
      </section>
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
