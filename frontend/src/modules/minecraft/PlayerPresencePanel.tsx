/**
 * 玩家現場 — 在線玩家、背包／裝備、活動訊息流。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchMinecraftPlayerDetail,
  fetchMinecraftPlayerEvents,
  fetchMinecraftPlayers,
  type MinecraftObservabilityEvent,
  type MinecraftPlayerDetail,
  type MinecraftPlayerSummary,
  type MinecraftPlayersSnapshot,
} from '../../api/linkin';
import { KpiSparkCard } from '../../components/ui/monitor';
import {
  ConsoleCard,
  ConsoleCardHeader,
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  KpiGrid6,
  PanelAlert,
  PanelShell,
  SectionHeader,
} from '../../components/ui/ConsoleLayout';
import {
  BridgeSetupBanner,
  CopyButton,
  EmptyStateCta,
  bridgeLiveReady,
  formatTs,
  minecraftHref,
  playerActionLabel,
  statusLabel,
  statusStripe,
  useVisibilityPoll,
} from './monitor/shared';
import QuestRuntimeStrip from './QuestRuntimeStrip';

const PLAYER_ACTIONS = ['', 'join', 'quit', 'move', 'chat', 'death', 'inventory', 'teleport', 'pickup', 'drop', 'block_break', 'block_place'];

const INGEST_WEBHOOK_PATH = '/linkin/minecraft/players/ingest';

/** 優先 API 設定；否則用目前站台 hostname:25565（略過 localhost）。 */
function resolveJoinAddressHint(fromApi?: string | null): string | null {
  const configured = (fromApi || '').trim();
  if (configured) return configured;
  if (typeof window === 'undefined') return null;
  const host = window.location.hostname;
  if (!host || host === 'localhost' || host === '127.0.0.1') return null;
  return `${host}:25565`;
}


const INGEST_EXAMPLES: Array<{ label: string; body: Record<string, unknown> }> = [
  {
    label: 'player/chat',
    body: { action: 'chat', player: 'Steve', message: '大家好！', summary: 'Steve: 大家好！' },
  },
  {
    label: 'player/death',
    body: {
      action: 'death',
      player: 'Alex',
      summary: 'Alex 被殭屍擊敗',
      cause: 'zombie',
      position: { x: 120, y: 64, z: -30 },
    },
  },
  {
    label: 'player/block_break',
    body: {
      action: 'block_break',
      player: 'Steve',
      block: 'DIAMOND_ORE',
      summary: 'Steve 破壞了鑽石礦',
      position: { x: 50, y: 12, z: 80 },
    },
  },
  {
    label: 'player/block_place',
    body: {
      action: 'block_place',
      player: 'Alex',
      block: 'OAK_PLANKS',
      summary: 'Alex 放置了橡木木板',
      position: { x: 10, y: 64, z: 20 },
    },
  },
];

function posText(pos?: { x?: number; y?: number; z?: number } | null): string {
  if (!pos) return '—';
  return `${Math.round(pos.x ?? 0)}, ${Math.round(pos.y ?? 0)}, ${Math.round(pos.z ?? 0)}`;
}

function isIngestedEvent(evt: MinecraftObservabilityEvent): boolean {
  const details = evt.details as Record<string, unknown> | undefined;
  return details?.source === 'ingest';
}

function InventoryGrid({ detail }: { detail: MinecraftPlayerDetail }) {
  const slots = detail.slots ?? [];
  const armor = detail.armor ?? [];
  const held = detail.held;
  const slotMap = new Map<number | string, { name: string; count: number }>();
  for (const item of slots) {
    if (item.slot != null) slotMap.set(item.slot, { name: item.name, count: item.count });
  }

  return (
    <div className="space-y-3 text-xs">
      <div>
        <p className="mb-1 text-[10px] text-[var(--console-faint)]">主手</p>
        <div className="rounded border border-[var(--console-border)] bg-black/20 px-2 py-1.5">
          {held ? `${held.name} ×${held.count}` : '—'}
        </div>
      </div>
      <div>
        <p className="mb-1 text-[10px] text-[var(--console-faint)]">裝備</p>
        <div className="grid grid-cols-2 gap-1 sm:grid-cols-4">
          {armor.length ? (
            armor.map((item, idx) => (
              <div key={`${item.slot ?? idx}-${item.name}`} className="rounded border border-[var(--console-border)] bg-black/20 px-2 py-1">
                {item.name} ×{item.count}
              </div>
            ))
          ) : (
            <span className="text-[var(--console-faint)]">無裝備資料</span>
          )}
        </div>
      </div>
      <div>
        <p className="mb-1 text-[10px] text-[var(--console-faint)]">背包（{slots.length} 格有物品）</p>
        <div className="grid grid-cols-3 gap-1 sm:grid-cols-6 md:grid-cols-9">
          {Array.from({ length: 36 }, (_, idx) => {
            const item = slotMap.get(idx) ?? slotMap.get(String(idx));
            return (
              <div
                key={idx}
                className="flex min-h-[2.5rem] flex-col justify-center rounded border border-[var(--console-border)] bg-black/20 px-1 py-0.5 text-[9px]"
                title={item ? `${item.name} ×${item.count}` : `slot ${idx}`}
              >
                <span className="text-[var(--console-faint)]">{idx}</span>
                {item ? <span className="truncate text-[var(--console-text)]">{item.name}</span> : null}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function PlayerPresencePanel() {
  const [snapshot, setSnapshot] = useState<MinecraftPlayersSnapshot | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MinecraftPlayerDetail | null>(null);
  const [events, setEvents] = useState<MinecraftObservabilityEvent[]>([]);
  const [actionFilter, setActionFilter] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadPlayers = useCallback(async () => {
    setError(null);
    try {
      const data = await fetchMinecraftPlayers(true);
      setSnapshot(data);
      if (!selectedId && data.players.length) {
        setSelectedId(data.players[0].id);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  const loadEvents = useCallback(async () => {
    try {
      const res = await fetchMinecraftPlayerEvents({
        limit: 40,
        action: actionFilter || undefined,
        player_id: selectedId || undefined,
      });
      setEvents(res.events.slice().reverse());
    } catch (err) {
      setError((err as Error).message);
    }
  }, [actionFilter, selectedId]);

  const loadDetail = useCallback(async (playerId: string) => {
    try {
      const res = await fetchMinecraftPlayerDetail(playerId, true);
      if (res.ok && res.player) setDetail(res.player);
      else setDetail(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useVisibilityPoll(loadPlayers, 5000);
  useVisibilityPoll(loadEvents, 4000);

  useEffect(() => {
    if (selectedId) void loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  const bridgeOffline = Boolean(snapshot?.bridge_offline);
  const bridgeLive = bridgeLiveReady(snapshot?.bridge);
  const onlineDisplay = bridgeLive ? String(snapshot?.online_count ?? 0) : '待接橋';
  const players = snapshot?.players ?? [];
  const selected = useMemo(
    () => players.find((p) => p.id === selectedId) ?? null,
    [players, selectedId],
  );
  const ingestedCount = events.filter(isIngestedEvent).length;
  const joinAddress = resolveJoinAddressHint(snapshot?.join_address);

  return (
    <PanelShell scroll={false}>
      <ConsoleCenterColumn>
        <ConsoleColumnScroll>
          {error ? <PanelAlert tone="error">{error}</PanelAlert> : null}

          {bridgeOffline ? (
            <div className="mb-3">
              <BridgeSetupBanner bridge={snapshot?.bridge} />
            </div>
          ) : null}

          <ConsoleCard className="mb-3">
            <ConsoleCardHeader>橋接狀態</ConsoleCardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2 px-3 pb-3 text-xs">
              <div className="text-[var(--console-muted)]">
                <div>
                  狀態：
                  <span className={bridgeOffline ? 'text-[var(--console-amber)]' : 'text-[var(--console-green)]'}>
                    {bridgeOffline ? '離線／未啟用' : snapshot?.bridge?.connected ? '已連線' : '—'}
                  </span>
                </div>
                <div className="mt-0.5 text-[10px] text-[var(--console-faint)]">
                  {bridgeOffline
                    ? '不會捏造玩家位置；可透過下方 ingest 接入 chat／death／方塊事件。'
                    : '每 5s 輪詢 MineMCP 更新在線玩家與背包。'}
                </div>
              </div>
              {bridgeOffline ? (
                <a href={minecraftHref('bridge_monitor')} className="console-btn text-xs">
                  打開橋接監控
                </a>
              ) : (
                <a href={minecraftHref('minecraft')} className="console-btn-ghost text-xs">
                  橋接操作
                </a>
              )}
            </div>
          </ConsoleCard>

          {bridgeOffline ? (
            <PanelAlert tone="notice">
              MineMCP 橋接離線或未啟用 — 不會捏造玩家位置或背包。已 ingest 的活動事件仍會顯示。
            </PanelAlert>
          ) : null}

          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <SectionHeader title="玩家現場" className="mb-0" />
            <span className="text-[9px] text-[var(--console-faint)]">
              {loading ? '刷新中…' : snapshot?.generated_at ? `更新 ${formatTs(snapshot.generated_at)} · 5s` : '自動刷新 5s'}
            </span>
          </div>

          <KpiGrid6>
            <KpiSparkCard
              label="在線玩家"
              value={onlineDisplay}
              accent={bridgeLive && Boolean(snapshot?.online_count)}
              spark={bridgeLive ? [0, 1, snapshot?.online_count ?? 0, snapshot?.online_count ?? 0] : [0, 0, 0, 0]}
            />
            <KpiSparkCard label="橋接" value={bridgeOffline ? '離線' : snapshot?.bridge?.connected ? '已連線' : '—'} accent={!bridgeOffline} />
            <KpiSparkCard label="活動事件" value={String(events.length)} />
            <KpiSparkCard label="Ingest 事件" value={String(ingestedCount)} accent={ingestedCount > 0} />
          </KpiGrid6>

          {bridgeOffline && !players.length ? (
            <EmptyStateCta
              title="尚無即時玩家資料"
              hint="設定 EVOL_MC_MCP_* 並探測連線；或使用 POST /minecraft/players/ingest 接入插件 webhook。"
              actions={[
                { label: '橋接健康', href: minecraftHref('bridge_monitor'), primary: true },
                { label: '橋接操作', href: minecraftHref('minecraft') },
              ]}
            />
          ) : null}

          {!bridgeOffline && !players.length && !loading ? (
            <EmptyStateCta
              title="目前沒有玩家在線"
              hint={
                joinAddress
                  ? `伺服器目前為空。在 Minecraft「多人遊戲」加入 ${joinAddress} 即可上線；面板會在約 5 秒內刷新。`
                  : '伺服器目前為空。請用多人遊戲加入本機 Paper 伺服器（預設埠 25565）即可上線；亦可設定 EVOL_MC_JOIN_ADDRESS 顯示公開位址。'
              }
              actions={[
                { label: '打開伺服器地圖', href: minecraftHref('server-map') },
                { label: '橋接健康', href: minecraftHref('bridge_monitor') },
              ]}
            />
          ) : null}

          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>外部事件接入</ConsoleCardHeader>
            <div className="space-y-3 px-3 pb-3 text-xs text-[var(--console-muted)]">
              <p>
                橋接無法推送 chat／death／方塊事件。請讓 Bukkit 插件或腳本 POST 至下方路徑（模組閘道：
                <code className="mx-1 rounded bg-black/30 px-1">/modules/minecraft/api/minecraft/players/ingest</code>）。
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <code className="rounded bg-black/30 px-2 py-1 font-mono text-[10px]">POST {INGEST_WEBHOOK_PATH}</code>
                <CopyButton text={INGEST_WEBHOOK_PATH} label="複製路徑" />
              </div>
              <div className="space-y-2">
                {INGEST_EXAMPLES.map((example) => (
                  <div key={example.label} className="rounded border border-[var(--console-border)] bg-black/15 p-2">
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="font-mono text-[10px] text-[var(--console-accent)]">{example.label}</span>
                      <CopyButton text={JSON.stringify(example.body, null, 2)} label="複製 JSON" />
                    </div>
                    <pre className="max-h-28 overflow-auto font-mono text-[9px] text-[var(--console-faint)]">
                      {JSON.stringify(example.body, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          </ConsoleCard>

          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <ConsoleCard>
              <ConsoleCardHeader>在線玩家</ConsoleCardHeader>
              <ul className="divide-y divide-[var(--console-border)]">
                {!players.length ? (
                  <li className="px-3 py-4 text-xs text-[var(--console-faint)]">
                    <div>
                      {bridgeOffline
                        ? '橋接未就緒 — 無即時在線列表（非世界為空）'
                        : '目前沒有玩家在線'}
                    </div>
                    {!bridgeOffline && joinAddress ? (
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px]">
                        <span>加入伺服器：</span>
                        <code className="rounded bg-black/30 px-1.5 py-0.5 font-mono">{joinAddress}</code>
                        <CopyButton text={joinAddress} label="複製位址" />
                      </div>
                    ) : null}
                  </li>
                ) : (
                  players.map((player: MinecraftPlayerSummary) => (
                    <li key={player.id}>
                      <button
                        type="button"
                        className={`mon-task-card w-full px-3 py-2 text-left text-xs ${selectedId === player.id ? 'bg-[var(--console-accent)]/10' : ''}`}
                        onClick={() => setSelectedId(player.id)}
                      >
                        <div className="flex justify-between gap-2">
                          <span className="font-medium">{player.name}</span>
                          <span className="text-[var(--console-faint)]">{player.gamemode ?? '—'}</span>
                        </div>
                        <div className="mt-0.5 text-[var(--console-muted)]">
                          {player.dimension ?? player.world ?? '?'} · {posText(player.position)}
                        </div>
                        <div className="text-[10px] text-[var(--console-faint)]">
                          HP {player.health ?? '—'} · 飽食 {player.food ?? '—'} · {formatTs(player.last_seen)}
                        </div>
                      </button>
                    </li>
                  ))
                )}
              </ul>
            </ConsoleCard>

            <ConsoleCard>
              <ConsoleCardHeader>
                {selected ? `${selected.name} · 詳情` : '玩家詳情'}
              </ConsoleCardHeader>
              <div className="px-3 pb-3">
                {!selected ? (
                  <p className="text-xs text-[var(--console-faint)]">選擇左側玩家查看背包</p>
                ) : detail ? (
                  <>
                    <dl className="mb-3 grid grid-cols-2 gap-2 text-[11px]">
                      <div><dt className="text-[var(--console-faint)]">UUID</dt><dd className="truncate font-mono">{detail.uuid ?? '—'}</dd></div>
                      <div><dt className="text-[var(--console-faint)]">維度</dt><dd>{detail.dimension ?? detail.world ?? '—'}</dd></div>
                      <div><dt className="text-[var(--console-faint)]">座標</dt><dd>{posText(detail.position)}</dd></div>
                      <div><dt className="text-[var(--console-faint)]">生命／飽食</dt><dd>{detail.health ?? '—'} / {detail.food ?? '—'}</dd></div>
                    </dl>
                    <InventoryGrid detail={detail} />
                  </>
                ) : (
                  <p className="text-xs text-[var(--console-faint)]">載入中或無詳情（橋接離線）</p>
                )}
              </div>
            </ConsoleCard>
          </div>

          {selectedId ? (
            <ConsoleCard className="mt-3">
              <ConsoleCardHeader title={`${selected?.name ?? selectedId} · 任務進度`} />
              <QuestRuntimeStrip playerId={selectedId} />
            </ConsoleCard>
          ) : null}

          <ConsoleCard className="mt-3">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--console-border)] px-3 py-2">
              <ConsoleCardHeader className="border-0 p-0">活動訊息流</ConsoleCardHeader>
              <div className="flex flex-wrap items-center gap-2">
                <label className="text-[10px] text-[var(--console-faint)]">
                  類型
                  <select
                    value={actionFilter}
                    onChange={(e) => setActionFilter(e.target.value)}
                    className="ml-1 rounded border border-[var(--console-border)] bg-black/20 px-1 py-0.5 text-[10px]"
                  >
                    {PLAYER_ACTIONS.map((a) => (
                      <option key={a || 'all'} value={a}>{a ? playerActionLabel(a) : '全部'}</option>
                    ))}
                  </select>
                </label>
                <button type="button" className="console-btn-ghost text-xs" onClick={() => void loadEvents()}>
                  刷新
                </button>
              </div>
            </div>
            {!events.length ? (
              <p className="px-3 py-3 text-xs text-[var(--console-faint)]">
                尚無玩家活動 — 玩家上線／移動／背包變更會自動記錄；亦可 POST ingest 接入插件。
              </p>
            ) : (
              <ul className="divide-y divide-[var(--console-border)] px-1 pb-2">
                {events.map((evt) => {
                  const ingested = isIngestedEvent(evt);
                  return (
                    <li
                      key={evt.id}
                      className={`mon-task-card px-2 py-2 text-xs ${ingested ? 'border-l-2 border-l-[var(--console-accent)] bg-[var(--console-accent)]/5' : ''}`}
                      data-priority={statusStripe(evt.status)}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[10px] text-[var(--console-faint)]">{formatTs(evt.ts)}</span>
                        <span className="rounded bg-[var(--console-card)] px-1.5 py-0.5 text-[10px]">
                          {playerActionLabel(evt.action)}
                        </span>
                        {ingested ? (
                          <span className="rounded bg-[var(--console-accent)]/15 px-1.5 py-0.5 text-[10px] text-[var(--console-accent)]">
                            Ingest
                          </span>
                        ) : null}
                        <span className="text-[var(--console-accent)]">{statusLabel(evt.status)}</span>
                      </div>
                      <p className="mt-1 text-[var(--console-text)]">{evt.summary}</p>
                    </li>
                  );
                })}
              </ul>
            )}
          </ConsoleCard>
        </ConsoleColumnScroll>
      </ConsoleCenterColumn>
    </PanelShell>
  );
}
