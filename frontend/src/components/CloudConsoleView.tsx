/**
 * CloudConsoleView — 雲控制台分頁視圖（監控 / 實例 / 告警 / 事件）
 * 費用帳單已整合至靈境積分中心（#/monitor/credits/cloud）
 */
import { useState } from 'react';
import AlertsPanel from './AlertsPanel';
import DockerView from './DockerView';
import EventsPanel from './EventsPanel';
import MonitoringPanel from './MonitoringPanel';
import { jumpToCreditsSection } from '../lib/billingUi';
import {
  ConsoleSection,
  ConsoleSectionNav,
  ConsoleTabBody,
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

export default function CloudConsoleView({ embedded = false }: { embedded?: boolean }) {
  const [tab, setTab] = useState<CloudTab>('monitoring');
  const activeId = CLOUD_SECTIONS.find((s) => s.key === tab)?.id ?? CLOUD_SECTIONS[0].id;

  const content = (
    <div className={consoleLayout.sectionStack + ' min-h-0 flex-1 overflow-hidden'}>
      {!embedded ? (
        <button
          type="button"
          onClick={() => jumpToCreditsSection('cloud')}
          className="w-full rounded-xl border border-[#64D2FF]/25 bg-[#64D2FF]/5 px-3 py-2 text-left text-[11px] text-[#AEAEB2] hover:bg-[#64D2FF]/10"
        >
          <span className="text-[#64D2FF]">費用帳單</span> 已整合至靈境積分中心 → 雲與 Docker（Docker 按時 + 阿里雲 BSS）
        </button>
      ) : null}

      {tab === 'monitoring' ? (
        <ConsoleSection id="cloud-monitoring" title="資源監控" description="CPU · 記憶體 · 網路">
          <MonitoringPanel embedded />
        </ConsoleSection>
      ) : null}
      {tab === 'instances' ? (
        <ConsoleSection id="cloud-instances" title="實例管理" description="容器啟停 · 日誌">
          <DockerView embedded />
        </ConsoleSection>
      ) : null}
      {tab === 'alerts' ? (
        <ConsoleSection id="cloud-alerts" title="告警中心" description="閾值規則 · 歷史">
          <AlertsPanel embedded />
        </ConsoleSection>
      ) : null}
      {tab === 'events' ? (
        <ConsoleSection id="cloud-events" title="事件時間線" description="start · stop · restart">
          <EventsPanel embedded />
        </ConsoleSection>
      ) : null}
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
      <ConsoleSectionNav
        sections={CLOUD_SECTIONS.map((s) => ({ id: s.id, label: s.label }))}
        activeId={activeId}
        onSelect={(id) => {
          const next = CLOUD_SECTIONS.find((s) => s.id === id);
          if (next) setTab(next.key);
        }}
      />
      <ConsoleTabBody>{content}</ConsoleTabBody>
    </PanelShell>
  );
}
