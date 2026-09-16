/**
 * Minecraft 監控面板共用 hook 與狀態樣式。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchMinecraftAiEvents,
  fetchMinecraftMonitorSummary,
  type MinecraftAiMonitorKpis,
  type MinecraftMonitorSummary,
  type MinecraftObservabilityEvent,
} from '../../../api/linkin';

const LAST_MAP_URL_KEY = 'linkin.minecraft.lastMapUrl';

export function statusStripe(status: string): 'p1' | 'p2' | 'p3' | 'idle' {
  const s = status.toLowerCase();
  if (['failed', 'error', 'bridge_offline', 'cancelled', 'build_failed'].includes(s)) return 'p1';
  if (['partial', 'skipped', 'pending', 'pending_world', 'pending_builder'].includes(s)) return 'p2';
  if (['ok', 'applied', 'complete', 'built', 'dispatched'].includes(s)) return 'p3';
  return 'idle';
}

const PLAYER_ACTION_LABELS: Record<string, string> = {
  join: '上線',
  quit: '下線',
  move: '移動',
  teleport: '傳送',
  inventory: '背包變更',
  chat: '聊天',
  death: '死亡',
  pickup: '拾取',
  drop: '丟棄',
  block_break: '破壞方塊',
  block_place: '放置方塊',
};

export function playerActionLabel(action: string): string {
  return PLAYER_ACTION_LABELS[action] ?? action;
}

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    ok: '正常',
    applied: '已落地',
    partial: '部分',
    failed: '失敗',
    skipped: '略過',
    dry_run: '乾跑',
    bridge_offline: '橋接離線',
    pending_world: '待落地',
    pending_builder: '待建築',
    cancelled: '已取消',
    error: '錯誤',
    reachable: '可連線',
    unreachable: '無法連線',
  };
  return map[status] ?? status;
}

export function formatTs(ts?: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString('zh-Hant', { hour12: false });
}

/** Minecraft 模組內頁 deep link */
export function minecraftHref(page: string): string {
  return `#/modules/minecraft/${page}`;
}

export const BRIDGE_ENV_SNIPPET = `# Linkin → MineMCP 橋接（後端環境變數）
EVOL_MC_MCP_ENABLED=true
EVOL_MC_MCP_URL=http://127.0.0.1:3000
EVOL_MC_MCP_TOKEN=<與 plugins/MineMCP/config.yml 相同>
EVOL_MC_MCP_WORLD=world
EVOL_MC_MCP_RPC_PATH=/sse`;

export const BRIDGE_SYSTEMD_SNIPPET = `[Service]
# 追加至 systemd drop-in（例如 /etc/systemd/system/linkin.service.d/minecraft.conf）
Environment=EVOL_MC_MCP_ENABLED=true
Environment=EVOL_MC_MCP_URL=http://127.0.0.1:3000
Environment=EVOL_MC_MCP_TOKEN=<YOUR_TOKEN>
Environment=EVOL_MC_MCP_WORLD=world`;

export const MAP_NGINX_SNIPPET = `# 將地圖反代到 Linkin 同源路徑（解決 X-Frame-Options / CSP）
location /minecraft-map/ {
    proxy_pass http://127.0.0.1:8123/;
    proxy_set_header Host $host;
    proxy_hide_header X-Frame-Options;
    # 若仍有 CSP frame-ancestors 問題，可視需要調整 Content-Security-Policy
}`;

export function rememberLastMapUrl(url: string): void {
  const trimmed = url.trim();
  if (!trimmed) return;
  try {
    localStorage.setItem(LAST_MAP_URL_KEY, trimmed);
  } catch {
    /* ignore quota / private mode */
  }
}

export function loadLastMapUrl(): string | null {
  try {
    return localStorage.getItem(LAST_MAP_URL_KEY);
  } catch {
    return null;
  }
}

/** 標籤隱藏時暫停輪詢 */
export function useVisibilityPoll(load: () => void | Promise<void>, pollMs = 12000) {
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === 'visible') {
        void loadRef.current();
      }
    };
    void loadRef.current();
    if (!pollMs) return undefined;
    const id = window.setInterval(tick, pollMs);
    const onVis = () => {
      if (document.visibilityState === 'visible') void loadRef.current();
    };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [pollMs]);
}

export function useMonitorSummary(pollMs = 12000) {
  const [data, setData] = useState<MinecraftMonitorSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const summary = await fetchMinecraftMonitorSummary();
      if (!summary?.kpis || typeof summary.kpis !== 'object') {
        throw new Error('監控摘要格式異常（缺少 kpis）');
      }
      setData(summary);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useVisibilityPoll(load, pollMs);

  return { data, error, loading, reload: load };
}

export function useAiEvents(limit = 20, pollMs = 10000) {
  const [events, setEvents] = useState<MinecraftObservabilityEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchMinecraftAiEvents({ limit });
      setEvents((res.events ?? []).slice().reverse());
    } catch (err) {
      setError((err as Error).message);
    }
  }, [limit]);

  useVisibilityPoll(load, pollMs);

  return { events, error, reload: load };
}

export type BridgeLike = {
  enabled?: boolean;
  connected?: boolean;
  dry_run?: boolean;
  token_configured?: boolean;
};

export function bridgeNeedsSetup(
  bridge?: BridgeLike | null,
  setup?: { all_ready?: boolean; token_set?: boolean } | null,
): boolean {
  if (!bridge) return true;
  if (!bridge.enabled) return true;
  if (!bridge.token_configured && !setup?.token_set) return true;
  if (bridge.dry_run) return true;
  if (!bridge.connected) return true;
  if (setup && setup.all_ready === false) return true;
  return false;
}

/** 可信任 MineMCP 即時玩家／世界 KPI */
export function bridgeLiveReady(bridge?: BridgeLike | null): boolean {
  return Boolean(bridge?.enabled && bridge?.token_configured && bridge?.connected && !bridge?.dry_run);
}

const AI_GM_STATUS_LABELS: Record<string, string> = {
  offline: '離線',
  'dry-run': '乾跑',
  active: '執行中',
  idle: '待命中',
};

export function aiGmStatusLabel(status: string | undefined): string {
  if (!status) return '—';
  return AI_GM_STATUS_LABELS[status] ?? status;
}

export function formatAiGmLastAction(kpis: MinecraftAiMonitorKpis | undefined): string {
  if (!kpis?.gm_last_run_ts) return '—';
  const n = kpis.gm_last_action_count ?? 0;
  const mode = kpis.gm_last_dry_run ? '乾跑' : kpis.gm_last_applied ? '已套用' : '記錄';
  const trigger = kpis.gm_last_trigger_action ? ` · ${kpis.gm_last_trigger_action}` : '';
  return `${n} 動作 · ${mode}${trigger}`;
}

export function bridgeKpi(bridge: MinecraftMonitorSummary['bridge'] | undefined) {
  if (!bridge?.enabled) return { label: '待設定', pct: 0, color: 'var(--console-faint)' };
  if (!bridge.token_configured) return { label: '待 Token', pct: 8, color: 'var(--console-amber)' };
  if (bridge.connected) return { label: '線上', pct: 100, color: 'var(--console-green)' };
  if (bridge.dry_run) return { label: '乾跑', pct: 55, color: 'var(--console-amber)' };
  return { label: '離線', pct: 12, color: 'var(--console-red)' };
}

export type BridgeSetup = NonNullable<MinecraftMonitorSummary['bridge_setup']>;

export function formatBridgeProbeLine(
  setup?: BridgeSetup | null,
  probe?: { ok?: boolean; connected?: boolean; dry_run?: boolean; message?: string; error?: string } | null,
): string {
  const fromProbe = String(probe?.message || probe?.error || '').trim();
  const fromSetup = String(setup?.probe_message || '').trim();
  const msg = fromProbe || fromSetup;
  const isDry = Boolean(probe?.dry_run ?? setup?.dry_run);
  if (isDry) {
    if (msg) return msg;
    return '本地乾跑探測：未向 MineMCP 發送 JSON-RPC';
  }
  if (setup?.connected || probe?.connected) {
    return msg || 'MineMCP 已連線';
  }
  if (msg) return msg;
  if (setup?.enabled && setup?.all_ready) {
    return '已啟用但未連線 — 請確認 MineMCP 插件是否運行';
  }
  return '請完成環境變數 checklist 後再探測';
}

export function formatBridgeAuditLine(row: {
  tool?: string;
  ok?: boolean;
  error?: string;
  dry_run?: boolean;
}): string {
  const tool = row.tool ?? 'bridge';
  if (row.dry_run && (tool.includes('probe') || row.error === 'bridge_offline')) {
    return `${tool} · 本地乾跑探測（未連線 MineMCP）`;
  }
  if (row.ok) return `${tool} · 成功`;
  return `${tool} · ${row.error || '失敗'}`;
}

export function CopyButton({ text, label = '複製' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* fallback ignored */
    }
  };
  return (
    <button type="button" className="console-btn-ghost text-[10px]" onClick={() => void onCopy()}>
      {copied ? '已複製' : label}
    </button>
  );
}

export function EmptyStateCta({
  title,
  hint,
  actions,
}: {
  title: string;
  hint?: string;
  actions: Array<{ label: string; href: string; primary?: boolean }>;
}) {
  return (
    <div className="rounded-lg border border-dashed border-[var(--console-border)] bg-[var(--console-card)] px-3 py-3 text-xs">
      <p className="font-medium text-[var(--console-text)]">{title}</p>
      {hint ? <p className="mt-1 text-[var(--console-faint)]">{hint}</p> : null}
      <div className="mt-2 flex flex-wrap gap-2">
        {actions.map((action) => (
          <a
            key={action.href}
            href={action.href}
            className={
              action.primary
                ? 'rounded-md border border-[var(--console-accent)]/40 bg-[var(--console-accent)]/10 px-2 py-1 text-[var(--console-accent)]'
                : 'console-btn-ghost rounded-md px-2 py-1'
            }
          >
            {action.label}
          </a>
        ))}
      </div>
    </div>
  );
}

export function BridgeSetupBanner({
  setup,
  bridge,
}: {
  setup?: BridgeSetup | null;
  bridge?: BridgeLike | null;
}) {
  if (!bridgeNeedsSetup(bridge, setup)) return null;
  const missing: string[] = [];
  if (!bridge?.enabled && !setup?.enabled) missing.push('EVOL_MC_MCP_ENABLED');
  if (!bridge?.token_configured && !setup?.token_set) missing.push('EVOL_MC_MCP_TOKEN');
  if (bridge?.dry_run || setup?.dry_run) missing.push('實際連線（目前為乾跑或未啟用）');
  else if (!bridge?.connected && !setup?.connected) missing.push('MineMCP 連線');
  return (
    <EmptyStateCta
      title="MineMCP 橋接尚未就緒"
      hint={
        missing.length
          ? `待完成：${missing.join('、')}。完成設定並 Ping 探測後，監控 KPI 才會反映伺服器現場。`
          : '請在橋接健康頁完成環境變數並探測連線。'
      }
      actions={[
        { label: '橋接健康與設定指南', href: minecraftHref('bridge_monitor'), primary: true },
        {
          label: '文件：minecraft-mcp.md',
          href: 'https://github.com/iiooiioo888/Linkin/blob/master/docs/linkin/minecraft-mcp.md',
        },
      ]}
    />
  );
}

export function BridgeSetupCard({
  setup,
  probe,
  compact = false,
  onProbe,
  probing = false,
}: {
  setup?: BridgeSetup | null;
  probe?: { ok?: boolean; connected?: boolean; dry_run?: boolean; message?: string; error?: string } | null;
  compact?: boolean;
  onProbe?: () => void;
  probing?: boolean;
}) {
  const rows = [
    { key: 'EVOL_MC_MCP_ENABLED', ok: setup?.enabled, label: 'ENABLED' },
    { key: 'EVOL_MC_MCP_URL', ok: setup?.url_set, label: 'URL' },
    { key: 'EVOL_MC_MCP_TOKEN', ok: setup?.token_set, label: 'TOKEN' },
    { key: 'EVOL_MC_MCP_WORLD', ok: setup?.world_set, label: 'WORLD' },
  ];
  const probeText = formatBridgeProbeLine(setup, probe);

  return (
    <div className={compact ? 'text-xs' : ''}>
      <ul className="space-y-1">
        {rows.map((row) => (
          <li key={row.key} className="flex items-center justify-between gap-2 border-b border-[var(--console-border)] py-1">
            <span className="font-mono text-[10px] text-[var(--console-muted)]">{row.key}</span>
            <span className={row.ok ? 'text-[var(--console-green)]' : 'text-[var(--console-faint)]'}>
              {row.ok ? '已設定' : '未設定'}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[var(--console-muted)]">
        探測：{probeText}
      </p>
      {!compact && (
        <div className="mt-2 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] text-[var(--console-faint)]">環境變數範例</span>
            <CopyButton text={BRIDGE_ENV_SNIPPET} />
          </div>
          <pre className="max-h-28 overflow-auto rounded bg-black/30 p-2 font-mono text-[9px] text-[var(--console-muted)]">
            {BRIDGE_ENV_SNIPPET}
          </pre>
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] text-[var(--console-faint)]">systemd drop-in</span>
            <CopyButton text={BRIDGE_SYSTEMD_SNIPPET} />
          </div>
          <pre className="max-h-20 overflow-auto rounded bg-black/30 p-2 font-mono text-[9px] text-[var(--console-muted)]">
            {BRIDGE_SYSTEMD_SNIPPET}
          </pre>
          <a
            href="https://github.com/iiooiioo888/Linkin/blob/master/docs/linkin/minecraft-mcp.md"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] text-[var(--console-accent)] hover:underline"
          >
            完整橋接文件 →
          </a>
        </div>
      )}
      {onProbe && (
        <button
          type="button"
          className="console-btn-ghost mt-2 text-xs"
          disabled={probing}
          onClick={onProbe}
        >
          {probing ? '探測中…' : 'Ping 探測'}
        </button>
      )}
    </div>
  );
}

export function PipelineTimeline({ events }: { events: MinecraftObservabilityEvent[] }) {
  if (!events.length) return null;
  return (
    <ol className="relative border-l border-[var(--console-border)] pl-3 text-xs">
      {events.map((evt) => {
        const stripe = statusStripe(evt.status);
        const steps = (evt.details?.steps as Array<{ id?: string; status?: string; message?: string }>) ?? [];
        return (
          <li key={evt.id} className="mb-3 last:mb-0">
            <span
              className="absolute -left-1.5 mt-1 h-2.5 w-2.5 rounded-full border border-[var(--console-border)] bg-[var(--console-bg)]"
              data-priority={stripe}
            />
            <div className="text-[var(--console-faint)]">{formatTs(evt.ts)}</div>
            <div className="mt-0.5">
              <span className="font-mono text-[10px]">{evt.domain}/{evt.action}</span>
              <span className="ml-2 text-[var(--console-accent)]">{statusLabel(evt.status)}</span>
            </div>
            <p className="mt-0.5 text-[var(--console-text)]">{evt.summary}</p>
            {steps.length > 0 && (
              <ul className="mt-1 space-y-0.5 text-[10px] text-[var(--console-muted)]">
                {steps.slice(0, 8).map((step) => (
                  <li key={step.id}>
                    {step.id}: {statusLabel(String(step.status ?? ''))}
                    {step.message ? ` — ${step.message}` : ''}
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export function MapEmbedHelp({ onUseLastUrl }: { onUseLastUrl?: () => void }) {
  const lastUrl = loadLastMapUrl();
  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[11px] text-[var(--console-muted)]">
      <p className="font-medium text-amber-300">地圖可能無法內嵌（X-Frame-Options / CSP）</p>
      <p className="mt-1">
        若探測成功但 iframe 空白，多半是地圖站點阻擋跨域嵌入。請用 nginx 反代到 Linkin 同源路徑，或改用「新分頁開啟」。
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <CopyButton text={MAP_NGINX_SNIPPET} label="複製 nginx 片段" />
        <a
          href="https://github.com/iiooiioo888/Linkin/blob/master/docs/linkin/minecraft-plugins.md"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--console-accent)] hover:underline"
        >
          文件說明
        </a>
        {lastUrl && onUseLastUrl && (
          <button type="button" className="console-btn-ghost text-[10px]" onClick={onUseLastUrl}>
            使用上次成功 URL
          </button>
        )}
      </div>
      <pre className="mt-2 max-h-24 overflow-auto rounded bg-black/30 p-2 font-mono text-[9px]">
        {MAP_NGINX_SNIPPET}
      </pre>
    </div>
  );
}
