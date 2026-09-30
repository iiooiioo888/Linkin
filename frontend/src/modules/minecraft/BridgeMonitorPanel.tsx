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
import AiEventsPanel from './monitor/AiEventsPanel';
import { McHeader, McLinks, McPage, McPanel } from './McChrome';
import {
  BridgeSetupCard,
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
            error: e.bridge_offline ? 'bridge_offline' : (e.details?.error as string),
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

  const probeLine = formatBridgeProbeLine(setup, status?.probe ?? undefined);
  const setupPending = bridgeNeedsSetup(status ?? undefined, setup);
  const headline = status?.connected
    ? 'MineMCP 已連線，可以對世界做落地操作。'
    : status?.dry_run
      ? '目前是乾跑：呼叫只記審計，不會寫進世界。'
      : status?.enabled
        ? '橋接已啟用，但還沒連上 MineMCP。'
        : '橋接尚未啟用。';

  const facts = [
    status?.url ? { label: '位址', value: status.url.replace(/\/\/[^@]+@/, '//***@') } : null,
    status?.world ? { label: '世界', value: status.world } : null,
    { label: '即時寫入', value: status?.live ? '可以' : '不行' },
    { label: '乾跑', value: status?.dry_run ? '是' : '否' },
  ].filter((row): row is { label: string; value: string } => Boolean(row));

  return (
    <McPage>
      <McHeader
        title="橋接健康"
        lead="MineMCP 是否啟用、憑證是否齊、探測是否真的打到伺服器。這裡不顯示密鑰。"
        aside={
          <button type="button" className="rd-btn" disabled={busy} onClick={() => void onProbe()}>
            {busy ? '探測中…' : '探測連線'}
          </button>
        }
      />
      {error ? <p className="mc-error">{error}</p> : null}
      {setupPending ? (
        <p className="mc-note">設定還沒完成。補齊環境變數後再探測，監控才會反映伺服器現場。</p>
      ) : null}

      <McPanel title="連線">
        <p className="mc-note">{headline}</p>
        {probeLine ? <p className="mc-note" style={{ marginTop: 8 }}>{probeLine}</p> : null}
        <dl className="mc-facts" style={{ marginTop: 12 }}>
          {facts.map((fact) => (
            <div key={fact.label}>
              <dt>{fact.label}</dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>
      </McPanel>

      <McPanel title="環境變數">
        <BridgeSetupCard setup={setup} probe={status?.probe} onProbe={() => void onProbe()} probing={busy} />
      </McPanel>

      <McPanel title="最近紀錄">
        {!bridgeEvents.length ? (
          <p className="mc-empty">探測或呼叫工具之後，紀錄會出現在這裡。</p>
        ) : (
          <ul className="mc-list">
            {bridgeEvents.slice(0, 12).map((row, idx) => (
              <li key={`${row.ts}-${idx}`} className="mc-row">
                {row.ts ? <p className="mc-row__meta">{formatTs(Number(row.ts))}</p> : null}
                <p className={row.ok || row.dry_run ? 'mc-note' : 'mc-error'}>{formatBridgeAuditLine(row)}</p>
              </li>
            ))}
          </ul>
        )}
      </McPanel>

      <AiEventsPanel compact />
      <McLinks links={[{ href: minecraftHref('minecraft'), label: '打開橋接操作', primary: true }]} />
    </McPage>
  );
}
