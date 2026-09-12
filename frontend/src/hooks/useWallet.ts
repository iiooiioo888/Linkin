/**
 * 靈境積分帳務輪詢（/billing + /wallet 相容）。
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchBilling, fetchBillingLedger, fetchBillingUsage } from '../api/client';
import type { BillingAccount, BillingDockerSummary, BillingLedgerEntry, BillingUsageEvent } from '../types';

export function useWallet(pollMs = 8000) {
  const [account, setAccount] = useState<BillingAccount | null>(null);
  const [ledger, setLedger] = useState<BillingLedgerEntry[]>([]);
  const [usage, setUsage] = useState<BillingUsageEvent[]>([]);
  const [plans, setPlans] = useState<Record<string, unknown>[]>([]);
  const [docker, setDocker] = useState<BillingDockerSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [billing, ledgerResp, usageResp] = await Promise.all([
        fetchBilling(),
        fetchBillingLedger(30),
        fetchBillingUsage(30),
      ]);
      setAccount(billing.account);
      setPlans(billing.plans ?? []);
      setDocker(billing.docker ?? null);
      setLedger(ledgerResp.entries);
      setUsage(usageResp.events);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '讀取帳務失敗');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (!cancelled) await refresh();
    };
    void run();
    const timer = setInterval(() => void run(), pollMs);
    const onWalletRefresh = () => {
      void run();
    };
    window.addEventListener('linkin:wallet-refresh', onWalletRefresh);
    return () => {
      cancelled = true;
      clearInterval(timer);
      window.removeEventListener('linkin:wallet-refresh', onWalletRefresh);
    };
  }, [pollMs, refresh]);

  return { account, ledger, usage, plans, docker, loading, error, refresh };
}
