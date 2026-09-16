/**
 * Minecraft 監控總覽 — KPI、管線、橋接與 AI 可見事件。
 */
import { KpiSparkCard, ResourceGauges, StackBar } from '../../components/ui/monitor';
import {
  ConsoleCard,
  ConsoleCardHeader,
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  KpiGrid6,
  PanelAlert,
  PanelShell,
  SectionHeader,
  WarnBar,
} from '../../components/ui/ConsoleLayout';
import AiEventsPanel from './monitor/AiEventsPanel';
import SituationStrip from './SituationStrip';
import {
  BridgeSetupBanner,
  BridgeSetupCard,
  EmptyStateCta,
  PipelineTimeline,
  aiGmStatusLabel,
  bridgeKpi,
  bridgeLiveReady,
  bridgeNeedsSetup,
  formatAiGmLastAction,
  formatTs,
  minecraftHref,
  statusLabel,
  useMonitorSummary,
} from './monitor/shared';

export default function MonitorHubPanel() {
  const { data, error, loading, reload } = useMonitorSummary(12000);
  const bridge = bridgeKpi(data?.bridge);
  const ws = data?.world_status ?? {};
  const npcPending = ws.npcs?.pending_world ?? 0;
  const questPending = ws.quests?.pending_world ?? 0;
  const itemPending = ws.items?.pending_world ?? 0;
  const intentStack = [
    { label: 'NPC', value: npcPending, color: 'var(--console-green)' },
    { label: '任務', value: questPending, color: 'var(--console-blue)' },
    { label: '道具', value: itemPending, color: 'var(--console-cyan)' },
  ];
  const lastPipe = data?.last_pipeline;
  const timeline = data?.pipeline_timeline ?? [];
  const plugins = data?.plugins;
  const kpis = data?.kpis;
  const pendingBuild = kpis?.pending_build_briefs ?? 0;
  const pendingWorld = kpis?.pending_world_intents ?? 0;
  const playersLive = kpis?.players_live;
  const onlinePlayers = playersLive?.online_count ?? kpis?.online_players ?? data?.players?.online_count ?? 0;
  const summaryReady = Boolean(data) && !loading;
  const recentPlayerEvents = playersLive?.recent_events ?? 0;
  const aiKpi = kpis?.ai;
  const aiStatus = aiKpi?.gm_status ?? 'offline';
  const aiEvents24h = aiKpi?.events_24h ?? 0;
  const aiAccent = aiStatus === 'active' || aiStatus === 'idle';
  const mapUrl = plugins?.map_url?.trim() || '';
  const bridgeSetupPending = bridgeNeedsSetup(data?.bridge, data?.bridge_setup);
  const bridgeLive = bridgeLiveReady(data?.bridge);
  const bridgeOffline = Boolean(data?.bridge?.enabled && !data?.bridge?.connected && !data?.bridge?.dry_run);
  const kpiBridgeHold = !bridgeLive;
  const liveKpi = (n: number | undefined) => (kpiBridgeHold ? '待接橋' : String(n ?? 0));

  const emptyActions: Array<{ show: boolean; title: string; hint?: string; actions: Array<{ label: string; href: string; primary?: boolean }> }> = [
    {
      show: summaryReady && !lastPipe && !timeline.length,
      title: '尚無管線執行紀錄',
      hint: '從敘事工作區執行 Phase 0–5 一鍵管線，或手動生成／提交草稿。',
      actions: [
        { label: '前往敘事工作區', href: minecraftHref('narrative'), primary: true },
      ],
    },
    {
      show: summaryReady && !mapUrl,
      title: '尚未設定伺服器地圖 URL',
      hint: '在插件中心啟用 Dynmap／BlueMap 並填寫公開 URL。',
      actions: [
        { label: '打開插件中心', href: minecraftHref('plugin-hub'), primary: true },
        { label: '伺服器地圖', href: minecraftHref('server-map') },
      ],
    },
    {
      show: summaryReady && bridgeSetupPending,
      title: data?.bridge?.enabled ? 'MineMCP 橋接尚未就緒' : 'MineMCP 尚未啟用',
      hint: '監控上的「0」不代表世界為空，而是橋接未連線。請完成 EVOL_MC_MCP_* 設定並 Ping 探測。',
      actions: [
        { label: '橋接健康監控', href: minecraftHref('bridge_monitor'), primary: true },
        { label: '橋接操作面板', href: minecraftHref('minecraft') },
      ],
    },
    {
      show: summaryReady && bridgeOffline,
      title: 'MineMCP 已啟用但離線',
      hint: '插件未運行或 Token／URL 錯誤。落地操作將失敗或僅記錄審計。',
      actions: [{ label: '橋接健康監控', href: minecraftHref('bridge_monitor'), primary: true }],
    },
    {
      show: summaryReady && pendingBuild > 0,
      title: `待建築意圖 ${pendingBuild} 筆`,
      hint: '可在建築落地監控查看進度，或從敘事管線觸發 apply。',
      actions: [
        { label: '建築落地監控', href: minecraftHref('build_monitor'), primary: true },
        { label: '敘事工作區', href: minecraftHref('narrative') },
      ],
    },
    {
      show: summaryReady && pendingWorld > 0,
      title: `待世界意圖 ${pendingWorld} 筆`,
      hint: 'NPC／任務／道具待落地，可在對應監控或敘事工作區確認。',
      actions: [
        { label: '任務／道具監控', href: minecraftHref('quest_item_monitor'), primary: true },
        { label: 'NPC 監控', href: minecraftHref('npc_monitor') },
        { label: '敘事工作區', href: minecraftHref('narrative') },
      ],
    },
  ];

  return (
    <PanelShell scroll={false}>
      <ConsoleCenterColumn>
        <ConsoleColumnScroll>
          {error ? <PanelAlert tone="error">{error}</PanelAlert> : null}
          {data?.recent_errors?.length ? (
            <WarnBar>
              近期異常 {data.recent_errors.length} 筆 · 最後：{data.recent_errors[0]?.summary}
            </WarnBar>
          ) : null}

          {summaryReady && bridgeSetupPending ? (
            <div className="mb-3">
              <BridgeSetupBanner bridge={data?.bridge} setup={data?.bridge_setup} />
            </div>
          ) : null}

          <ConsoleCard className="mb-3">
            <div className="px-3 py-2">
              <SituationStrip />
            </div>
          </ConsoleCard>

          <div className="mb-2 flex items-center justify-between gap-2">
            <SectionHeader title="KPI 總覽" className="mb-0" />
            <span className="text-[9px] text-[var(--console-faint)]">
              {loading ? '刷新中…' : data?.generated_at ? `更新 ${formatTs(data.generated_at)}` : '自動刷新 12s'}
            </span>
          </div>
            <KpiGrid6>
            <KpiSparkCard
              label="在線玩家"
              value={liveKpi(onlinePlayers)}
              accent={!kpiBridgeHold && Boolean(onlinePlayers)}
              spark={kpiBridgeHold ? [0, 0, 0, 0] : [0, 1, onlinePlayers, onlinePlayers]}
            />
            <KpiSparkCard
              label="待建築意圖"
              value={String(pendingBuild)}
              accent={Boolean(pendingBuild)}
              spark={[2, 3, 2, 4, pendingBuild]}
            />
            <KpiSparkCard
              label="待世界意圖"
              value={String(pendingWorld)}
              accent={Boolean(pendingWorld)}
              spark={[1, 2, 3, 2, pendingWorld]}
            />
            <KpiSparkCard label="地圖計畫" value={String(kpis?.map_plan_count ?? 0)} />
            <KpiSparkCard label="NPC" value={String(kpis?.npc_count ?? 0)} />
            <KpiSparkCard label="任務" value={String(kpis?.quest_count ?? 0)} />
            <KpiSparkCard label="道具" value={String(kpis?.item_count ?? 0)} />
          </KpiGrid6>

          <div className="mt-3 mb-2 flex flex-wrap items-center justify-between gap-2">
            <SectionHeader title="AI 監控" className="mb-0" />
            <div className="flex flex-wrap gap-2 text-[10px]">
              <a href={minecraftHref('ai_gm')} className="rounded-md border border-[var(--console-border)] px-2 py-0.5 text-[var(--console-accent)] hover:underline">
                AI 主持人
              </a>
              <a href={minecraftHref('bridge_monitor')} className="rounded-md border border-[var(--console-border)] px-2 py-0.5 text-[var(--console-muted)] hover:underline">
                橋接事件
              </a>
            </div>
          </div>
          <KpiGrid6>
            <KpiSparkCard
              label="AI 事件（24h）"
              value={String(aiEvents24h)}
              accent={aiEvents24h > 0}
              spark={[1, 2, 3, 2, aiEvents24h]}
            />
            <KpiSparkCard
              label="AI 狀態"
              value={aiGmStatusLabel(aiStatus)}
              accent={aiAccent}
              spark={aiStatus === 'offline' ? [0, 0, 0, 0] : [1, 2, 2, 3]}
            />
            <KpiSparkCard
              label="GM 最近動作"
              value={formatAiGmLastAction(aiKpi)}
              accent={Boolean(aiKpi?.gm_last_applied)}
            />
            <KpiSparkCard
              label="GM 冷卻"
              value={aiKpi?.gm_enabled ? `${aiKpi.gm_cooldown_seconds ?? 30}s` : '—'}
            />
            <KpiSparkCard
              label="GM 決策（24h）"
              value={String(aiKpi?.gm_runs_24h ?? 0)}
              accent={Boolean(aiKpi?.gm_runs_24h)}
            />
            <KpiSparkCard
              label="GM 模式"
              value={
                !aiKpi?.gm_enabled
                  ? '停用'
                  : aiKpi.gm_dry_run
                    ? '乾跑'
                    : aiKpi.gm_auto_apply
                      ? '自動套用'
                      : '手動'
              }
            />
          </KpiGrid6>
          {aiKpi?.situation_hint ? (
            <p className="mt-1 text-[10px] text-[var(--console-faint)]">
              情境：{aiKpi.situation_hint}
            </p>
          ) : null}
          <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-[10px] text-[var(--console-faint)]">
            <span>
              AI 可見事件與玩家 KPI 分開統計；在線玩家僅計真人，不含 GM／NPC 虛擬身分。
              {aiKpi?.gm_last_run_ts ? ` · GM 上次 ${formatTs(aiKpi.gm_last_run_ts)}` : ''}
            </span>
          </div>

          <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-[10px]">
            <span className="text-[var(--console-faint)]">
              玩家現場
              {kpiBridgeHold ? ' · 待接橋（KPI 非即時）' : playersLive?.bridge_offline ? ' · 橋接離線' : ' · 即時'}
              {recentPlayerEvents > 0 ? ` · 近期活動 ${recentPlayerEvents}` : ''}
            </span>
            <a href={minecraftHref('player_presence')} className="text-[var(--console-accent)] hover:underline">
              {kpiBridgeHold ? '設定橋接後查看在線玩家' : `在線 ${onlinePlayers}`} · 打開玩家現場 →
            </a>
          </div>

          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>橋接健康 · MineMCP</ConsoleCardHeader>
            <div className="flex flex-wrap items-center gap-4 px-3 pb-3">
              <ResourceGauges gauges={[{ label: 'BRIDGE', pct: bridge.pct, color: bridge.color }]} />
              <div className="text-xs text-[var(--console-muted)]">
                <div>狀態：{bridge.label}</div>
                <div>世界：{data?.bridge.world ?? '—'}</div>
                <div>Token：{data?.bridge.token_configured ? '已配置' : '未配置'}</div>
                <div>Dry-run：{data?.bridge.dry_run ? '是' : '否'}</div>
              </div>
            </div>
          </ConsoleCard>

          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>地圖插件 · {plugins?.active_map_plugin ?? '未選擇'}</ConsoleCardHeader>
            <div className="px-3 pb-3 text-xs text-[var(--console-muted)]">
              <div>地圖 URL：{mapUrl || '—'}</div>
              <div className="mt-1">
                可連線：{plugins?.reachable_count ?? 0} / 已配置：{plugins?.configured_count ?? 0}
              </div>
              {!mapUrl && (
                <a href={minecraftHref('plugin-hub')} className="mt-2 inline-block text-[var(--console-accent)] hover:underline">
                  前往插件中心設定 →
                </a>
              )}
            </div>
          </ConsoleCard>

          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>橋接設定 checklist</ConsoleCardHeader>
            <div className="px-3 pb-3">
              <BridgeSetupCard setup={data?.bridge_setup} compact />
              <a
                href={minecraftHref('bridge_monitor')}
                className="mt-2 inline-block text-[10px] text-[var(--console-accent)] hover:underline"
              >
                完整設定指南 →
              </a>
            </div>
          </ConsoleCard>

          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>世界意圖待落地</ConsoleCardHeader>
            <div className="px-3 pb-3">
              <StackBar segments={intentStack} />
            </div>
          </ConsoleCard>

          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>地圖與布局</ConsoleCardHeader>
            <div className="flex flex-wrap items-center gap-2 px-3 pb-3 text-xs">
              <span className="text-[var(--console-muted)]">
                地圖計畫 {kpis?.map_plan_count ?? 0} 筆
              </span>
              <a href={minecraftHref('layout-preview')} className="console-btn">
                布局預覽
              </a>
              {(kpis?.map_plan_count ?? 0) === 0 ? (
                <>
                  <a href={minecraftHref('narrative')} className="console-btn-ghost">
                    生成敘事／地圖
                  </a>
                  <a href={minecraftHref('server-map')} className="console-btn-ghost">
                    伺服器地圖
                  </a>
                </>
              ) : null}
            </div>
          </ConsoleCard>

          {emptyActions.filter((a) => a.show).map((block) => (
            <EmptyStateCta key={block.title} title={block.title} hint={block.hint} actions={block.actions} />
          ))}

          <SectionHeader title="最近管線步驟" className="mt-3" />
          <ConsoleCard>
            {timeline.length > 0 ? (
              <div className="px-3 pb-3">
                <PipelineTimeline events={timeline} />
              </div>
            ) : lastPipe ? (
              <div className="px-3 pb-3 text-xs">
                <div className="text-[var(--console-faint)]">{formatTs(lastPipe.ts)}</div>
                <div className="mt-1">
                  [{lastPipe.domain}/{lastPipe.action}] {statusLabel(lastPipe.status)}
                </div>
                <p className="mt-1 text-[var(--console-text)]">{lastPipe.summary}</p>
              </div>
            ) : (
              <p className="px-3 pb-3 text-xs text-[var(--console-faint)]">尚無管線事件</p>
            )}
          </ConsoleCard>

          <AiEventsPanel />

          <button type="button" className="console-btn-ghost mt-2 text-xs" onClick={() => void reload()}>
            手動刷新
          </button>
        </ConsoleColumnScroll>
      </ConsoleCenterColumn>
    </PanelShell>
  );
}
