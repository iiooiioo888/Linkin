/**
 * Minecraft 監控面板共用 hook 與狀態樣式。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchMinecraftAiEvents,
  fetchMinecraftMonitorSummary,
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
      setData(await fetchMinecraftMonitorSummary());
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
      setEvents(res.events.slice().reverse());
    } catch (err) {
      setError((err as Error).message);
    }
  }, [limit]);

  useVisibilityPoll(load, pollMs);

  return { events, error, reload: load };
}

export function bridgeKpi(bridge: MinecraftMonitorSummary['bridge'] | undefined) {
  if (!bridge?.enabled) return { label: '未啟用', pct: 0, color: 'var(--console-faint)' };
  if (bridge.connected) return { label: '線上', pct: 100, color: 'var(--console-green)' };
  if (bridge.dry_run) return { label: 'Dry-run', pct: 55, color: 'var(--console-amber)' };
  return { label: '離線', pct: 12, color: 'var(--console-red)' };
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

type BridgeSetup = NonNullable<MinecraftMonitorSummary['bridge_setup']>;

export function BridgeSetupCard({
  setup,
  compact = false,
  onProbe,
  probing = false,
}: {
  setup?: BridgeSetup | null;
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
  const probeText = setup?.probe_message
    ? setup.probe_message
    : setup?.connected
      ? 'MineMCP 已連線'
      : setup?.dry_run
        ? '乾跑模式：未向 MineMCP 發送探測'
        : setup?.enabled && setup?.all_ready
          ? '已啟用但未連線 — 請檢查 MineMCP 是否運行'
          : '請完成上方 checklist 後再探測';

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
