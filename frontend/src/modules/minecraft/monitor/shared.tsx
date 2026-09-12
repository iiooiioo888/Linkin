/**
 * Minecraft 監控面板共用 hook 與狀態樣式。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  fetchMinecraftAiEvents,
  fetchMinecraftMonitorSummary,
  type MinecraftMonitorSummary,
  type MinecraftObservabilityEvent,
} from '../../../api/linkin';

export function statusStripe(status: string): 'p1' | 'p2' | 'p3' | 'idle' {
  const s = status.toLowerCase();
  if (['failed', 'error', 'bridge_offline', 'cancelled', 'build_failed'].includes(s)) return 'p1';
  if (['partial', 'skipped', 'pending', 'pending_world', 'pending_builder'].includes(s)) return 'p2';
  if (['ok', 'applied', 'complete', 'built', 'dispatched'].includes(s)) return 'p3';
  return 'idle';
}

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    ok: '正常',
    applied: '已落地',
    partial: '部分',
    failed: '失敗',
    skipped: '略過',
    dry_run: 'Dry-run',
    bridge_offline: '橋接離線',
    pending_world: '待落地',
    pending_builder: '待建築',
    cancelled: '已取消',
  };
  return map[status] ?? status;
}

export function formatTs(ts?: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString('zh-Hant', { hour12: false });
}

export function useMonitorSummary(pollMs = 15000) {
  const [data, setData] = useState<MinecraftMonitorSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await fetchMinecraftMonitorSummary());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    if (!pollMs) return undefined;
    const id = window.setInterval(() => void load(), pollMs);
    return () => window.clearInterval(id);
  }, [load, pollMs]);

  return { data, error, loading, reload: load };
}

export function useAiEvents(limit = 20, pollMs = 12000) {
  const [events, setEvents] = useState<MinecraftObservabilityEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchMinecraftAiEvents({ limit });
      setEvents(res.events.slice().reverse());
    } catch (err) {
      setError((err as Error).message);
    }
  }, [limit]);

  useEffect(() => {
    void load();
    if (!pollMs) return undefined;
    const id = window.setInterval(() => void load(), pollMs);
    return () => window.clearInterval(id);
  }, [load, pollMs]);

  return { events, error, reload: load };
}

export function bridgeKpi(bridge: MinecraftMonitorSummary['bridge'] | undefined) {
  if (!bridge?.enabled) return { label: '未啟用', pct: 0, color: 'var(--console-faint)' };
  if (bridge.connected) return { label: '線上', pct: 100, color: 'var(--console-green)' };
  if (bridge.dry_run) return { label: 'Dry-run', pct: 55, color: 'var(--console-amber)' };
  return { label: '離線', pct: 12, color: 'var(--console-red)' };
}
