/**
 * 橋接健康監控 — EVOL_MC_MCP_* 配置、ping、最近錯誤（無密鑰）。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  fetchMinecraftAiEvents,
  fetchMinecraftStatus,
  probeMinecraft,
  type MinecraftAudit,
  type MinecraftStatus,
} from '../../api/linkin';
import { ResourceGauges } from '../../components/ui/monitor';
import {
  ConsoleCard,
  ConsoleCardHeader,
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  PanelAlert,
  PanelShell,
  WarnBar,
} from '../../components/ui/ConsoleLayout';
import AiEventsPanel from './monitor/AiEventsPanel';
import { bridgeKpi, formatTs } from './monitor/shared';

export default function BridgeMonitorPanel() {
  const [status, setStatus] = useState<MinecraftStatus | null>(null);
  const [bridgeEvents, setBridgeEvents] = useState<MinecraftAudit[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [st, ev] = await Promise.all([
        fetchMinecraftStatus(),
        fetchMinecraftAiEvents({ limit: 30 }),
      ]);
      setStatus(st);
      const audits = (st.recent ?? []) as MinecraftAudit[];
      const bridgeEv = ev.events.filter((e) => e.domain === 'bridge');
      setBridgeEvents(audits);
      if (bridgeEv.length) {
        setBridgeEvents(
          bridgeEv.map((e) => ({
            ts: String(e.ts),
            tool: `${e.domain}/${e.action}`,
            ok: e.status === 'ok',
            error: e.bridge_offline ? 'bridge_offline' : e.details?.error as string,
            dry_run: e.dry_run,
          })),
        );
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onProbe = async () => {
    setBusy(true);
    try {
      await probeMinecraft();
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const bridge = bridgeKpi(status ?? undefined);
  const envHints = [
    { key: 'EVOL_MC_MCP_ENABLED', ok: status?.enabled },
    { key: 'EVOL_MC_MCP_URL', ok: Boolean(status?.url) },
    { key: 'EVOL_MC_MCP_TOKEN', ok: status?.token_configured },
    { key: 'EVOL_MC_MCP_WORLD', ok: Boolean(status?.world) },
  ];

  return (
    <PanelShell>
      <ConsoleCenterColumn>
        <ConsoleColumnScroll>
          {error ? <PanelAlert tone="error">{error}</PanelAlert> : null}
          {!status?.connected && status?.enabled ? (
            <WarnBar>MineMCP 已啟用但未連線 — 落地操作將 dry-run 或失敗。</WarnBar>
          ) : null}
          <ConsoleCard>
            <div className="flex items-center justify-between gap-2 border-b border-[var(--console-border)] px-3 py-2">
              <ConsoleCardHeader className="border-0 p-0">橋接健康 · 狀態 / 探測 / 審計</ConsoleCardHeader>
              <button type="button" className="console-btn-ghost text-xs" disabled={busy} onClick={() => void onProbe()}>
                {busy ? '探測中…' : 'Ping 探測'}
              </button>
            </div>
            <div className="flex flex-wrap gap-4 px-3 pb-3">
              <ResourceGauges gauges={[{ label: 'MCP', pct: bridge.pct, color: bridge.color }]} />
              <div className="text-xs text-[var(--console-muted)]">
                <div>狀態：{bridge.label}</div>
                <div>URL：{status?.url ? status.url.replace(/\/\/[^@]+@/, '//***@') : '—'}</div>
                <div>世界：{status?.world ?? '—'}</div>
                <div>Live：{status?.live ? '是' : '否'} · Dry-run：{status?.dry_run ? '是' : '否'}</div>
              </div>
            </div>
          </ConsoleCard>
          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>環境配置 · 不顯示密鑰</ConsoleCardHeader>
            <ul className="px-3 pb-3 text-xs">
              {envHints.map((row) => (
                <li key={row.key} className="flex justify-between border-b border-[var(--console-border)] py-1.5">
                  <span className="font-mono text-[10px]">{row.key}</span>
                  <span className={row.ok ? 'text-[var(--console-green)]' : 'text-[var(--console-faint)]'}>
                    {row.ok ? '已配置' : '未配置 / 關閉'}
                  </span>
                </li>
              ))}
            </ul>
          </ConsoleCard>
          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>最近審計 / 錯誤</ConsoleCardHeader>
            {!bridgeEvents.length ? (
              <p className="px-3 pb-3 text-xs text-[var(--console-faint)]">尚無橋接事件</p>
            ) : (
              <ul className="divide-y divide-[var(--console-border)] text-xs">
                {bridgeEvents.slice(0, 12).map((row, idx) => (
                  <li key={`${row.ts}-${idx}`} className="px-3 py-2">
                    <div className="text-[var(--console-faint)]">{row.ts ? formatTs(Number(row.ts)) : '—'}</div>
                    <div className={row.ok ? 'text-[var(--console-green)]' : 'text-[var(--console-red)]'}>
                      {row.tool ?? 'bridge'} {row.ok ? 'ok' : 'error'}
                      {row.dry_run ? ' · dry-run' : ''}
                    </div>
                    {row.error ? <div className="text-[var(--console-red)]">{row.error}</div> : null}
                  </li>
                ))}
              </ul>
            )}
          </ConsoleCard>
          <AiEventsPanel compact />
          <p className="mt-2 text-xs text-[var(--console-faint)]">
            完整工具呼叫請使用「橋接」操作面板（#/modules/minecraft/bridge）。
          </p>
        </ConsoleColumnScroll>
      </ConsoleCenterColumn>
    </PanelShell>
  );
}
