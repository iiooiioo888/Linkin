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
  EmptyStateCta,
  formatTs,
  minecraftHref,
  statusLabel,
  statusStripe,
  useVisibilityPoll,
} from './monitor/shared';

const PLAYER_ACTIONS = ['', 'join', 'quit', 'move', 'chat', 'death', 'inventory', 'teleport', 'pickup', 'drop', 'block_break', 'block_place'];

function posText(pos?: { x?: number; y?: number; z?: number } | null): string {
  if (!pos) return '—';
  return `${Math.round(pos.x ?? 0)}, ${Math.round(pos.y ?? 0)}, ${Math.round(pos.z ?? 0)}`;
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
  const players = snapshot?.players ?? [];
  const selected = useMemo(
    () => players.find((p) => p.id === selectedId) ?? null,
    [players, selectedId],
  );

  return (
    <PanelShell scroll={false}>
      <ConsoleCenterColumn>
        <ConsoleColumnScroll>
          {error ? <PanelAlert tone="error">{error}</PanelAlert> : null}
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
              value={String(snapshot?.online_count ?? 0)}
              accent={Boolean(snapshot?.online_count)}
              spark={[0, 1, snapshot?.online_count ?? 0, snapshot?.online_count ?? 0]}
            />
            <KpiSparkCard label="橋接" value={bridgeOffline ? '離線' : snapshot?.bridge?.connected ? '已連線' : '—'} accent={!bridgeOffline} />
            <KpiSparkCard label="活動事件" value={String(events.length)} />
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

          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <ConsoleCard>
              <ConsoleCardHeader>在線玩家</ConsoleCardHeader>
              <ul className="divide-y divide-[var(--console-border)]">
                {!players.length ? (
                  <li className="px-3 py-4 text-xs text-[var(--console-faint)]">目前無在線玩家</li>
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
                      <option key={a || 'all'} value={a}>{a || '全部'}</option>
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
                {events.map((evt) => (
                  <li key={evt.id} className="mon-task-card px-2 py-2 text-xs" data-priority={statusStripe(evt.status)}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-[10px] text-[var(--console-faint)]">{formatTs(evt.ts)}</span>
                      <span className="rounded bg-[var(--console-card)] px-1.5 py-0.5 text-[10px]">
                        {evt.action}
                      </span>
                      <span className="text-[var(--console-accent)]">{statusLabel(evt.status)}</span>
                    </div>
                    <p className="mt-1 text-[var(--console-text)]">{evt.summary}</p>
                  </li>
                ))}
              </ul>
            )}
          </ConsoleCard>
        </ConsoleColumnScroll>
      </ConsoleCenterColumn>
    </PanelShell>
  );
}
