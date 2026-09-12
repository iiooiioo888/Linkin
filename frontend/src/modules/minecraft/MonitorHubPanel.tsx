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
import { bridgeKpi, formatTs, statusLabel, useMonitorSummary } from './monitor/shared';

export default function MonitorHubPanel() {
  const { data, error, loading, reload } = useMonitorSummary();
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

          <SectionHeader title="KPI 總覽" />
          <KpiGrid6>
            <KpiSparkCard
              label="待建築意圖"
              value={String(data?.kpis.pending_build_briefs ?? 0)}
              accent={Boolean(data?.kpis.pending_build_briefs)}
              spark={[2, 3, 2, 4, data?.kpis.pending_build_briefs ?? 0]}
            />
            <KpiSparkCard
              label="待世界意圖"
              value={String(data?.kpis.pending_world_intents ?? 0)}
              spark={[1, 2, 3, 2, data?.kpis.pending_world_intents ?? 0]}
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
              <a href="#/modules/minecraft/layout-preview" className="console-btn">
                布局預覽
              </a>
              {(data?.kpis.map_plan_count ?? 0) === 0 ? (
                <>
                  <a href="#/modules/minecraft/narrative" className="console-btn-ghost">
                    生成敘事／地圖
                  </a>
                  <a href="#/modules/minecraft/server-map" className="console-btn-ghost">
                    伺服器地圖
                  </a>
                </>
              ) : null}
            </div>
          </ConsoleCard>

          <SectionHeader title="最近管線步驟" className="mt-3" />
          <ConsoleCard>
            {lastPipe ? (
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

          {loading ? <p className="mt-2 text-xs text-[var(--console-faint)]">載入中…</p> : null}
          <button type="button" className="console-btn-ghost mt-2 text-xs" onClick={() => void reload()}>
            手動刷新
          </button>
        </ConsoleColumnScroll>
      </ConsoleCenterColumn>
    </PanelShell>
  );
}
