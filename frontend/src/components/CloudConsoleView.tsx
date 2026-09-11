/**
 * CloudConsoleView — 雲控制台（監控 / 實例 / 告警 / 事件）
 * 費用帳單已整合至靈境積分中心（#/monitor/credits/cloud）
 */
import { useState } from 'react';
import AlertsPanel from './AlertsPanel';
import DockerView from './DockerView';
import EventsPanel from './EventsPanel';
import MonitoringPanel from './MonitoringPanel';
import { jumpToCreditsSection } from '../lib/billingUi';
import {
  ConsoleLeftRail,
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  ConsoleRailNav,
  ConsoleRightRail,
  ConsoleSectionNav,
  ConsoleSnippetList,
  ConsoleThreeColumn,
  PanelShell,
  consoleLayout,
} from './ui/ConsoleLayout';

const CLOUD_SECTIONS = [
  { id: 'cloud-monitoring', key: 'monitoring' as const, label: '資源監控' },
  { id: 'cloud-instances', key: 'instances' as const, label: '實例管理' },
  { id: 'cloud-alerts', key: 'alerts' as const, label: '告警中心' },
  { id: 'cloud-events', key: 'events' as const, label: '事件時間線' },
] as const;

type CloudTab = (typeof CLOUD_SECTIONS)[number]['key'];

function CloudSectionBody({ tab }: { tab: CloudTab }) {
  if (tab === 'monitoring') return <MonitoringPanel embedded />;
  if (tab === 'instances') return <DockerView embedded />;
  if (tab === 'alerts') return <AlertsPanel embedded />;
  return <EventsPanel embedded />;
}

export default function CloudConsoleView({ embedded = false }: { embedded?: boolean }) {
  const [tab, setTab] = useState<CloudTab>('monitoring');
  const activeId = CLOUD_SECTIONS.find((s) => s.key === tab)?.id ?? CLOUD_SECTIONS[0].id;

  const content = (
    <div className={consoleLayout.pageContent}>
      {!embedded ? (
        <button
          type="button"
          onClick={() => jumpToCreditsSection('cloud')}
          className="mb-2 w-full rounded-lg border border-[var(--console-blue)]/25 bg-[var(--console-blue)]/5 px-3 py-2 text-left text-[11px] text-[var(--console-sub)] hover:bg-[var(--console-blue)]/10"
        >
          <span className="text-[var(--console-blue)]">費用帳單</span> 已整合至靈境積分中心 → 雲與 Docker
        </button>
      ) : null}
      <CloudSectionBody tab={tab} />
    </div>
  );

  if (embedded) {
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <ConsoleSectionNav
          sections={CLOUD_SECTIONS.map((s) => ({ id: s.id, label: s.label }))}
          activeId={activeId}
          onSelect={(id) => {
            const next = CLOUD_SECTIONS.find((s) => s.id === id);
            if (next) setTab(next.key);
          }}
          className="!static !z-0 !border-0 !bg-transparent !px-0 !py-0 !backdrop-blur-none"
        />
        {content}
      </div>
    );
  }

  return (
    <PanelShell scroll={false}>
      <ConsoleThreeColumn>
        <ConsoleLeftRail>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-4">
            <h1 className="text-[15px] font-semibold text-[var(--console-ink)]">雲控制台</h1>
            <p className="mt-1 text-[10px] text-[var(--console-faint)]">監控 · 實例 · 告警 · 事件</p>
          </div>
          <ConsoleColumnScroll className="!px-0 !py-0">
            <ConsoleRailNav
              sections={CLOUD_SECTIONS.map((s) => ({ id: s.id, label: s.label }))}
              activeId={activeId}
              onSelect={(id) => {
                const next = CLOUD_SECTIONS.find((s) => s.id === id);
                if (next) setTab(next.key);
              }}
            />
          </ConsoleColumnScroll>
        </ConsoleLeftRail>
        <ConsoleCenterColumn>
          <ConsoleColumnScroll>{content}</ConsoleColumnScroll>
        </ConsoleCenterColumn>
        <ConsoleRightRail>
          <ConsoleColumnScroll>
            <ConsoleSnippetList title="計費">
              <button
                type="button"
                onClick={() => jumpToCreditsSection('cloud')}
                className="text-left text-[11px] text-[var(--console-blue)]"
              >
                前往靈境積分 · 雲與 Docker
              </button>
            </ConsoleSnippetList>
          </ConsoleColumnScroll>
        </ConsoleRightRail>
      </ConsoleThreeColumn>
    </PanelShell>
  );
}
