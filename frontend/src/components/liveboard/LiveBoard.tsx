/**
 * LiveBoard — Agent Desk 觀測總覽（monitor dashboard v3）。
 */
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { fetchBillingOverview } from '../../api/client';
import { filterAgentsByDesk, requestRoleSettingsDesk } from '../../lib/agentUi';
import type { AnimLiveFeed } from '../../lib/animLive';
import { buildWorkflowSteps } from '../../lib/liveBoardFocus';
import { buildStatusStack, buildTaskDistributionMatrix } from '../../lib/monitorData';
import { useMediaQuery } from '../../hooks/useMediaQuery';
import { useMonitorStore } from '../../stores/monitorStore';
import type { L0Snapshot } from '../../types';
import type { MonitorTab } from '../AppShell';
import MonitorAlertMode from '../monitor/MonitorAlertMode';
import { PanelShell } from '../ui/ConsoleLayout';
import { MonitorStatusDot, MonitorStatusStrip } from '../ui/monitor';
import type { MonitorStatusTone } from '../ui/monitor';
import { CenterMain } from './center';
import { LiveBoardFocusGrid, WorkflowRail } from './focus';
import { LiveBoardDetailsToggle, RightRailContent } from './rails';
import type { LiveBoardDensity, LiveBoardNav } from './types';

function liveTone(feed: AnimLiveFeed): MonitorStatusTone {
  return feed.live ? 'ok' : 'idle';
}

export default function LiveBoard({
  feed,
  l0Snapshot = null,
  density = 'page',
  liteShell = false,
  onOpenLab,
  onOpenTab,
  onOpenTraces,
  onOpenAgent,
}: {
  feed: AnimLiveFeed;
  l0Snapshot?: L0Snapshot | null;
  density?: LiveBoardDensity;
  liteShell?: boolean;
} & LiveBoardNav) {
  const { t } = useTranslation();
  const [alertMode, setAlertMode] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [unhealthyKeys, setUnhealthyKeys] = useState(0);
  const dock = density === 'dock';
  const isMobile = useMediaQuery('(max-width: 767px)', false);

  useEffect(() => {
    if (dock) return;
    fetchBillingOverview()
      .then((o) => setUnhealthyKeys(o.unhealthy_keys_count))
      .catch(() => setUnhealthyKeys(0));
  }, [dock]);

  const dashboard = useMonitorStore((s) => s.dashboard);
  const connected = useMonitorStore((s) => s.connected);
  const consoleFeed = useMemo(
    () => ({ ...feed, agents: filterAgentsByDesk(feed.agents, 'console') }),
    [feed],
  );
  const taskMatrix = useMemo(
    () => buildTaskDistributionMatrix(dashboard?.tasks ?? []),
    [dashboard?.tasks],
  );
  const statusStack = useMemo(
    () => buildStatusStack(dashboard?.stats ?? {}),
    [dashboard?.stats],
  );
  const updated = consoleFeed.updatedAt
    ? new Date(consoleFeed.updatedAt).toLocaleTimeString('zh-TW', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : null;

  const opt = feed.optimization;
  const edge = opt?.edge_cache ?? opt?.opc_edge;
  const cacheCapPct = edge?.max_size ? ((edge?.entry_count ?? 0) / edge.max_size) * 100 : 0;
  const capacityFull = cacheCapPct >= 100;
  const cacheWarnText = capacityFull
    ? `⚠ 快取容量 ${Math.round(cacheCapPct)}% — 建議清理（${edge?.entry_count ?? 0}/${edge?.max_size ?? 512}）`
    : undefined;

  const handleAlertJump = (tab: MonitorTab, detail?: string) => {
    onOpenTab?.(tab);
    if (detail && tab === 'agents') onOpenAgent?.(detail);
  };

  const statusStripActions = (
    <>
      {!liteShell ? (
        <button
          type="button"
          onClick={() => setAlertMode(true)}
          className="mon-alert-btn"
          data-testid="monitor-alert-mode-toggle"
        >
          {t('monitorAlert.toggle')}
        </button>
      ) : null}
      <MonitorStatusDot tone={liveTone(feed)} label={feed.live ? 'LIVE' : 'IDLE'} />
    </>
  );

  const statusStripLeading = <span className="mon-live-status__eyebrow">即時總覽</span>;

  const workflowSteps = useMemo(
    () =>
      buildWorkflowSteps(consoleFeed, onOpenTab, () => {
        requestRoleSettingsDesk();
      }),
    [consoleFeed, onOpenTab],
  );

  const taskCount = dashboard?.tasks?.length ?? 0;

  const focusGrid = (
    <LiveBoardFocusGrid
      feed={feed}
      l0Snapshot={l0Snapshot}
      connected={connected}
      unhealthyKeys={unhealthyKeys}
      capacityFull={capacityFull}
      cacheWarnText={cacheWarnText}
      taskCount={taskCount}
      onOpenTab={onOpenTab}
      onOpenAgent={onOpenAgent}
      onOpenAlerts={liteShell ? undefined : () => setAlertMode(true)}
    />
  );

  const statusStrip = !dock ? (
    <MonitorStatusStrip
      leading={statusStripLeading}
      actions={statusStripActions}
      meta={updated ? <span className="font-mono tabular-nums">{updated}</span> : null}
    />
  ) : null;

  const liteHint = liteShell ? (
    <p className="mon-live-hint" title={t('mobileShell.alertModeDesktop')}>
      {t('mobileShell.alertModeDesktop')}
    </p>
  ) : null;

  const center = (
    <CenterMain
      feed={feed}
      consoleFeed={consoleFeed}
      taskMatrix={taskMatrix}
      statusStack={statusStack}
      capacityFull={capacityFull}
      cacheWarnText={cacheWarnText}
      dock={dock}
      liteShell={liteShell}
      onOpenTab={onOpenTab}
      onOpenTraces={onOpenTraces}
      onOpenAgent={onOpenAgent}
      onOpenLab={onOpenLab}
      showTaskStack={false}
    />
  );

  const right = (
    <RightRailContent
      feed={feed}
      consoleFeed={consoleFeed}
      statusStack={statusStack}
      onOpenTab={onOpenTab}
      onOpenAgent={onOpenAgent}
    />
  );

  const detailsBody = (
    <>
      <WorkflowRail steps={workflowSteps} onOpenTab={onOpenTab} />
      {center}
      {right}
    </>
  );

  const detailsPanel = !dock && !liteShell ? (
    <LiveBoardDetailsToggle open={detailsOpen} onToggle={() => setDetailsOpen((v) => !v)}>
      {detailsBody}
    </LiveBoardDetailsToggle>
  ) : (
    detailsBody
  );

  if (dock) {
    return (
      <div className="mon-live-shell flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-[var(--console-line)]">
        <MonitorAlertMode
          open={alertMode && !liteShell}
          onClose={() => setAlertMode(false)}
          onJump={handleAlertJump}
          unhealthyKeysCount={unhealthyKeys}
        />
        <div className="mon-live-mobile-scroll">
          <div className="mb-2 flex items-center gap-2">
            <MonitorStatusDot tone={liveTone(feed)} label={feed.live ? 'LIVE' : 'IDLE'} />
            {updated ? <span className="font-mono text-[10px] tabular-nums text-[var(--console-faint)]">{updated}</span> : null}
          </div>
          {focusGrid}
          {center}
        </div>
      </div>
    );
  }

  if (isMobile && !dock) {
    return (
      <PanelShell scroll={false}>
        <div className="mon-live-shell">
          <MonitorAlertMode
            open={alertMode && !liteShell}
            onClose={() => setAlertMode(false)}
            onJump={handleAlertJump}
            unhealthyKeysCount={unhealthyKeys}
          />
          {statusStrip}
          {liteHint}
          <div className="mon-live-mobile-scroll">
            {focusGrid}
            {detailsPanel}
          </div>
        </div>
      </PanelShell>
    );
  }

  return (
    <PanelShell scroll={false}>
      <div className="mon-live-shell">
        <MonitorAlertMode
          open={alertMode && !liteShell}
          onClose={() => setAlertMode(false)}
          onJump={handleAlertJump}
          unhealthyKeysCount={unhealthyKeys}
        />
        {statusStrip}
        {liteHint}
        <div className="mon-live-mobile-scroll mon-live-mobile-scroll--desktop">
          {focusGrid}
          {detailsPanel}
        </div>
      </div>
    </PanelShell>
  );
}
