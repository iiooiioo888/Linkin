/**
 * AI 主持人 — 玩家事件驅動任務進度與 NPC 回應。
 */
import { useCallback, useMemo, useState } from 'react';
import {
  fetchMinecraftGmConfig,
  fetchMinecraftGmRuns,
  fetchMinecraftPlayerEvents,
  reactMinecraftGm,
  tickMinecraftGm,
  updateMinecraftGmConfig,
  type MinecraftGmConfig,
  type MinecraftGmRun,
  type MinecraftObservabilityEvent,
} from '../../api/linkin';
import { KpiSparkCard } from '../../components/ui/monitor';
import {
  ConsoleCard,
  ConsoleCardHeader,
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  KpiGrid6,
  PanelAlert,
} from '../../components/ui/ConsoleLayout';
import { McHeader, McPage } from './McChrome';
import {
  EmptyStateCta,
  formatTs,
  minecraftHref,
  playerActionLabel,
  statusLabel,
  statusStripe,
  useVisibilityPoll,
} from './monitor/shared';
import QuestRuntimeStrip from './QuestRuntimeStrip';
import SituationStrip from './SituationStrip';

function actionTypeLabel(type: string): string {
  const map: Record<string, string> = {
    quest_progress: '任務進度',
    npc_say: 'NPC 發言',
    hint: '提示',
    player_assist: '玩家協助',
    region_focus: '區域焦點',
    noop: '無動作',
  };
  return map[type] || type;
}

function ConfigToggles({
  config,
  saving,
  onChange,
}: {
  config: MinecraftGmConfig;
  saving: boolean;
  onChange: (patch: Partial<MinecraftGmConfig>) => void;
}) {
  return (
    <div className="space-y-3 text-xs">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={config.enabled}
          disabled={saving}
          onChange={(e) => onChange({ enabled: e.target.checked })}
        />
        <span>啟用 AI 主持人</span>
        <span className="text-[var(--console-faint)]">（玩家事件到達時自動決策）</span>
      </label>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={config.dry_run}
          disabled={saving}
          onChange={(e) => onChange({ dry_run: e.target.checked })}
        />
        <span>僅記錄（Dry-run）</span>
        <span className="text-[var(--console-faint)]">不寫入任務、不發送遊戲內訊息</span>
      </label>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={config.auto_apply}
          disabled={saving || config.dry_run}
          onChange={(e) => onChange({ auto_apply: e.target.checked })}
        />
        <span className="text-[var(--console-amber)]">自動套用（危險）</span>
      </label>
      {config.auto_apply && !config.dry_run ? (
        <PanelAlert tone="notice">
          自動套用會經 MineMCP 發送 tellraw 並更新任務進度。請確認橋接已連線且世界狀態可接受。
        </PanelAlert>
      ) : null}
    </div>
  );
}

function RunRow({ run }: { run: MinecraftGmRun }) {
  const types = (run.actions || []).map((a) => actionTypeLabel(String(a.type || ''))).filter(Boolean).join('、') || '沒有動作';
  const applied = run.applied ? '已套用' : run.dry_run ? '乾跑' : '僅記錄';
  return (
    <div className="mon-task-card px-3 py-2" data-priority={statusStripe(run.status || 'idle')}>
      <div className="flex flex-wrap items-baseline justify-between gap-1">
        <span className="text-[11px] font-medium text-[var(--console-ink)]">
          {run.player_name || run.player_id || '未知玩家'} · {run.trigger_action ? playerActionLabel(run.trigger_action) : '未記錄動作'}
        </span>
        <span className="text-[10px] text-[var(--console-faint)]">{formatTs(run.ts)}</span>
      </div>
      <p className="mt-0.5 text-[10px] text-[var(--console-sub)]">
        {types} · {applied} · {statusLabel(run.status || 'ok')}
      </p>
      {run.rationale ? (
        <p className="mt-1 line-clamp-2 text-[10px] text-[var(--console-faint)]">{run.rationale}</p>
      ) : null}
    </div>
  );
}

export default function AiGmPanel() {
  const [config, setConfig] = useState<MinecraftGmConfig | null>(null);
  const [runs, setRuns] = useState<MinecraftGmRun[]>([]);
  const [playerEvents, setPlayerEvents] = useState<MinecraftObservabilityEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [acting, setActing] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(0);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [cfgRes, runsRes, evRes] = await Promise.all([
        fetchMinecraftGmConfig(),
        fetchMinecraftGmRuns(30),
        fetchMinecraftPlayerEvents({ limit: 20 }),
      ]);
      setConfig(cfgRes?.config ?? null);
      setRuns(runsRes?.runs ?? []);
      setPlayerEvents([...(evRes?.events ?? [])].reverse());
      setLastRefresh(Date.now());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useVisibilityPoll(load, 10000);

  const handleConfigChange = useCallback(
    async (patch: Partial<MinecraftGmConfig>) => {
      if (!config) return;
      const next = { ...config, ...patch };
      if (patch.dry_run && patch.dry_run) {
        next.auto_apply = false;
      }
      setSaving(true);
      setError(null);
      try {
        const res = await updateMinecraftGmConfig(next);
        setConfig(res.config);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setSaving(false);
      }
    },
    [config],
  );

  const handleTick = useCallback(async () => {
    setActing(true);
    setError(null);
    try {
      await tickMinecraftGm(5);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setActing(false);
    }
  }, [load]);

  const latestEvent = playerEvents[0];
  const handleReactLatest = useCallback(async () => {
    if (!latestEvent?.id) return;
    setActing(true);
    setError(null);
    try {
      await reactMinecraftGm(latestEvent.id, true);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setActing(false);
    }
  }, [latestEvent, load]);

  const appliedCount = useMemo(() => runs.filter((r) => r.applied).length, [runs]);

  return (
    <McPage>
      <McHeader
        title="AI 主持人"
        lead="玩家進場、對話或死亡會變成決策，再反映到任務與 NPC。預設只演練，不會直接改世界。"
        aside={
          <button type="button" className="mc-btn" onClick={() => void load()} disabled={loading}>
            {loading ? '讀取中' : lastRefresh ? `更新於 ${formatTs(lastRefresh / 1000)}` : '重新整理'}
          </button>
        }
      />
      <div className="mc-workspace">
        <ConsoleCenterColumn>
        <ConsoleColumnScroll>

          {error ? <PanelAlert tone="error">{error}</PanelAlert> : null}

          <ConsoleCard className="mb-3">
            <div className="px-3 py-2">
              <SituationStrip compact pollMs={10000} />
            </div>
          </ConsoleCard>

          {config ? (
          <KpiGrid6>
            <KpiSparkCard label="主持人" value={config.enabled ? '啟用' : '停用'} accent={Boolean(config.enabled)} />
            <KpiSparkCard label="套用" value={config.dry_run ? '演練' : config.auto_apply ? '自動' : '手動'} />
            <KpiSparkCard label="決策" value={String(runs.length)} />
            <KpiSparkCard label="已套用" value={String(appliedCount)} accent={appliedCount > 0} />
            <KpiSparkCard label="冷卻" value={`${config.cooldown_seconds} 秒`} />
            <KpiSparkCard label="每次上限" value={String(config.max_actions_per_event)} />
          </KpiGrid6>
          ) : null}

          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <ConsoleCard>
              <ConsoleCardHeader title="設定" />
              <div className="px-3 pb-3">
                {config ? (
                  <ConfigToggles config={config} saving={saving} onChange={(p) => void handleConfigChange(p)} />
                ) : (
                  <p className="text-xs text-[var(--console-faint)]">載入中…</p>
                )}
                <div className="mt-4 flex flex-wrap gap-2">
                  <button type="button" className="console-btn" disabled={acting || !config?.enabled} onClick={() => void handleTick()}>
                    {acting ? '處理中' : '跑一輪'}
                  </button>
                  <button
                    type="button"
                    className="console-btn-ghost"
                    disabled={acting || !latestEvent}
                    onClick={() => void handleReactLatest()}
                  >
                    回應最新事件
                  </button>
                </div>
              </div>
            </ConsoleCard>

            <ConsoleCard>
              <ConsoleCardHeader title="最近玩家事件" />
              <div className="max-h-48 space-y-1 overflow-y-auto px-3 pb-3">
                {!playerEvents.length ? (
                  <p className="text-xs text-[var(--console-faint)]">尚無玩家事件。</p>
                ) : (
                  playerEvents.slice(0, 8).map((evt) => (
                    <div key={evt.id} className="flex items-center justify-between gap-2 text-[10px]">
                      <span className="truncate text-[var(--console-sub)]">
                        {(evt.entity_refs?.player_name as string) || '?'} · {evt.action}: {evt.summary}
                      </span>
                      <button
                        type="button"
                        className="shrink-0 console-btn-ghost px-1 py-0 text-[9px]"
                        disabled={acting}
                        onClick={() => {
                          setActing(true);
                          void reactMinecraftGm(evt.id, true)
                            .then(() => load())
                            .catch((err) => setError((err as Error).message))
                            .finally(() => setActing(false));
                        }}
                      >
                        回應
                      </button>
                    </div>
                  ))
                )}
              </div>
            </ConsoleCard>
          </div>

          <ConsoleCard className="mt-3">
            <ConsoleCardHeader title="任務進度運行時" />
            <QuestRuntimeStrip compact />
          </ConsoleCard>

          <ConsoleCard className="mt-3">
            <ConsoleCardHeader title="GM 決策時間軸" />
            <div className="space-y-1 px-3 pb-3">
              {!runs.length ? (
                <EmptyStateCta
                  title="尚無 GM 決策"
                  hint="啟用 AI 主持人後，玩家 join／chat／death 等事件會觸發決策；或使用 Tick／React 手動測試。"
                  actions={[
                    { label: '玩家現場', href: minecraftHref('player_presence') },
                    { label: 'AI 事件', href: minecraftHref('monitor') },
                  ]}
                />
              ) : (
                runs.map((run) => <RunRow key={run.id} run={run} />)
              )}
            </div>
          </ConsoleCard>
        </ConsoleColumnScroll>
        </ConsoleCenterColumn>
      </div>
    </McPage>
  );
}
