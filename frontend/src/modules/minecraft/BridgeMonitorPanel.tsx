/**
 * 橋接健康監控 — EVOL_MC_MCP_* 配置、ping、最近錯誤（無密鑰）。
 */
import { useCallback, useState } from 'react';
import {
  fetchMinecraftAiEvents,
  fetchMinecraftMonitorSummary,
  fetchMinecraftStatus,
  probeMinecraft,
  type MinecraftAudit,
  type MinecraftBridgeSetup,
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
import {
  BridgeSetupCard,
  bridgeKpi,
  bridgeNeedsSetup,
  formatBridgeAuditLine,
  formatBridgeProbeLine,
  formatTs,
  minecraftHref,
  useVisibilityPoll,
} from './monitor/shared';

export default function BridgeMonitorPanel() {
  const [status, setStatus] = useState<MinecraftStatus | null>(null);
  const [setup, setSetup] = useState<MinecraftBridgeSetup | null>(null);
  const [bridgeEvents, setBridgeEvents] = useState<MinecraftAudit[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [st, ev, summary] = await Promise.all([
        fetchMinecraftStatus(),
        fetchMinecraftAiEvents({ limit: 30 }),
        fetchMinecraftMonitorSummary(),
      ]);
      setStatus(st);
      setSetup(summary.bridge_setup ?? null);
      const audits = (st.recent ?? []) as MinecraftAudit[];
      const bridgeEv = (ev.events ?? []).filter((e) => e.domain === 'bridge');
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

  useVisibilityPoll(load, 12000);

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
  const probeLine = formatBridgeProbeLine(setup, status?.probe ?? undefined);
  const setupPending = bridgeNeedsSetup(status ?? undefined, setup);
  const plainStatus = status?.connected
    ? 'MineMCP 已連線，可執行落地操作。'
    : status?.dry_run
      ? `乾跑模式：工具呼叫僅記錄審計，不寫入世界。${probeLine ? ` 探測：${probeLine}` : ''}`
      : status?.enabled
        ? `已啟用但未連線。${probeLine || '請確認 MineMCP 插件是否運行、Token 是否正確。'}`
        : '橋接未啟用：請設定 EVOL_MC_MCP_ENABLED=true 與 TOKEN。';

  return (
    <PanelShell>
      <ConsoleCenterColumn>
        <ConsoleColumnScroll>
          {error ? <PanelAlert tone="error">{error}</PanelAlert> : null}
          {setupPending ? (
            <WarnBar>
              橋接設定未完成或尚未連線 — 請依下方 checklist 設定環境變數；探測結果與審計會標示「本地乾跑」或「未連線」。
            </WarnBar>
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
                <div className="mt-2 rounded bg-[var(--console-card)] p-2 text-[var(--console-text)]">{plainStatus}</div>
              </div>
            </div>
          </ConsoleCard>
          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>環境配置 · 不顯示密鑰</ConsoleCardHeader>
            <div className="px-3 pb-3">
              <BridgeSetupCard setup={setup} probe={status?.probe} onProbe={() => void onProbe()} probing={busy} />
            </div>
          </ConsoleCard>
          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>最近審計 / 錯誤</ConsoleCardHeader>
            {!bridgeEvents.length ? (
              <p className="px-3 pb-3 text-xs text-[var(--console-faint)]">尚無橋接事件 — 探測或執行工具後會出現。</p>
            ) : (
              <ul className="divide-y divide-[var(--console-border)] text-xs">
                {bridgeEvents.slice(0, 12).map((row, idx) => (
                  <li key={`${row.ts}-${idx}`} className="px-3 py-2">
                    <div className="text-[var(--console-faint)]">{row.ts ? formatTs(Number(row.ts)) : '—'}</div>
                    <div className={row.ok || row.dry_run ? 'text-[var(--console-muted)]' : 'text-[var(--console-red)]'}>
                      {formatBridgeAuditLine(row)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </ConsoleCard>
          <AiEventsPanel compact />
          <p className="mt-2 text-xs text-[var(--console-faint)]">
            完整工具呼叫請使用「橋接」操作面板（<a href={minecraftHref('minecraft')} className="text-[var(--console-accent)] hover:underline">橋接</a>）。
          </p>
        </ConsoleColumnScroll>
      </ConsoleCenterColumn>
    </PanelShell>
  );
}
