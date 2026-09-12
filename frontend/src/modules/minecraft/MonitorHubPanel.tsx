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
import {
  BridgeSetupCard,
  EmptyStateCta,
  PipelineTimeline,
  bridgeKpi,
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
  const pendingBuild = data?.kpis.pending_build_briefs ?? 0;
  const pendingWorld = data?.kpis.pending_world_intents ?? 0;
  const mapUrl = plugins?.map_url?.trim() || '';
  const bridgeOffline = Boolean(data?.bridge?.enabled && !data?.bridge?.connected && !data?.bridge?.dry_run);

  const emptyActions: Array<{ show: boolean; title: string; hint?: string; actions: Array<{ label: string; href: string; primary?: boolean }> }> = [
    {
      show: !lastPipe && !timeline.length,
      title: '尚無管線執行紀錄',
      hint: '從敘事工作區執行 Phase 0–5 一鍵管線，或手動生成／提交草稿。',
      actions: [
        { label: '前往敘事工作區', href: minecraftHref('narrative'), primary: true },
      ],
    },
    {
      show: !mapUrl,
      title: '尚未設定伺服器地圖 URL',
      hint: '在插件中心啟用 Dynmap／BlueMap 並填寫公開 URL。',
      actions: [
        { label: '打開插件中心', href: minecraftHref('plugin-hub'), primary: true },
        { label: '伺服器地圖', href: minecraftHref('server-map') },
      ],
    },
    {
      show: bridgeOffline || (!data?.bridge?.enabled && !data?.bridge?.dry_run),
      title: data?.bridge?.enabled ? 'MineMCP 橋接離線' : 'MineMCP 尚未啟用',
      hint: '落地操作將 dry-run 或失敗。請設定 EVOL_MC_MCP_* 並探測連線。',
      actions: [
        { label: '橋接健康監控', href: minecraftHref('bridge_monitor'), primary: true },
        { label: '橋接操作面板', href: minecraftHref('minecraft') },
      ],
    },
    {
      show: pendingBuild > 0,
      title: `待建築意圖 ${pendingBuild} 筆`,
      hint: '可在建築落地監控查看進度，或從敘事管線觸發 apply。',
      actions: [
        { label: '建築落地監控', href: minecraftHref('build_monitor'), primary: true },
        { label: '敘事工作區', href: minecraftHref('narrative') },
      ],
    },
    {
      show: pendingWorld > 0,
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

          <div className="mb-2 flex items-center justify-between gap-2">
            <SectionHeader title="KPI 總覽" className="mb-0" />
            <span className="text-[9px] text-[var(--console-faint)]">
              {loading ? '刷新中…' : data?.generated_at ? `更新 ${formatTs(data.generated_at)}` : '自動刷新 12s'}
            </span>
          </div>
          <KpiGrid6>
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
            <KpiSparkCard label="地圖計畫" value={String(data?.kpis.map_plan_count ?? 0)} />
            <KpiSparkCard label="NPC" value={String(data?.kpis.npc_count ?? 0)} />
            <KpiSparkCard label="任務" value={String(data?.kpis.quest_count ?? 0)} />
            <KpiSparkCard label="道具" value={String(data?.kpis.item_count ?? 0)} />
          </KpiGrid6>

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
                地圖計畫 {data?.kpis.map_plan_count ?? 0} 筆
              </span>
              <a href={minecraftHref('layout-preview')} className="console-btn">
                布局預覽
              </a>
              {(data?.kpis.map_plan_count ?? 0) === 0 ? (
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
