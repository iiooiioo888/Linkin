/**
 * CloudConsoleView — 雲控制台單頁：監控 / 實例 / 告警 / 事件
 * 費用帳單已整合至靈境積分中心（#/monitor/credits/cloud）
 */
import { useCallback, useRef, useState } from 'react';
import AlertsPanel from './AlertsPanel';
import DockerView from './DockerView';
import EventsPanel from './EventsPanel';
import MonitoringPanel from './MonitoringPanel';
import {
  ConsoleSection,
  ConsoleSectionNav,
  PanelSection,
  PanelShell,
  PanelScroll,
  useScrollToSection,
  useSectionScrollSpy,
  consoleLayout,
} from './ui/ConsoleLayout';
import { jumpToCreditsSection } from '../lib/billingUi';

const CLOUD_SECTIONS = [
  { id: 'cloud-monitoring', label: '資源監控' },
  { id: 'cloud-instances', label: '實例管理' },
  { id: 'cloud-alerts', label: '告警中心' },
  { id: 'cloud-events', label: '事件時間線' },
] as const;

export default function CloudConsoleView({ embedded = false }: { embedded?: boolean }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollToInRoot = useScrollToSection(scrollRef);
  const spyActive = useSectionScrollSpy(CLOUD_SECTIONS.map((s) => s.id), scrollRef);
  const [clickedActive, setClickedActive] = useState<string>(CLOUD_SECTIONS[0].id);
  const activeId = embedded ? clickedActive : spyActive;

  const scrollTo = useCallback(
    (id: string) => {
      setClickedActive(id);
      if (embedded) {
        document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else {
        scrollToInRoot(id);
      }
    },
    [embedded, scrollToInRoot],
  );

  const sections = (
    <PanelSection className={consoleLayout.sectionGapLg}>
      <div className={embedded ? 'mb-3' : ''}>
        <button
          type="button"
          onClick={() => jumpToCreditsSection('cloud')}
          className="w-full rounded-xl border border-[#64D2FF]/25 bg-[#64D2FF]/5 px-3 py-2 text-left text-[11px] text-[#AEAEB2] hover:bg-[#64D2FF]/10"
        >
          <span className="text-[#64D2FF]">費用帳單</span> 已整合至靈境積分中心 → 雲與 Docker（Docker 按時 + 阿里雲 BSS）
        </button>
      </div>

      <ConsoleSection id="cloud-monitoring" title="資源監控" description="CPU · 記憶體 · 網路">
        <MonitoringPanel embedded />
      </ConsoleSection>

      <ConsoleSection id="cloud-instances" title="實例管理" description="容器啟停 · 日誌">
        <DockerView embedded />
      </ConsoleSection>

      <ConsoleSection id="cloud-alerts" title="告警中心" description="閾值規則 · 歷史">
        <AlertsPanel embedded />
      </ConsoleSection>

      <ConsoleSection id="cloud-events" title="事件時間線" description="start · stop · restart">
        <EventsPanel embedded />
      </ConsoleSection>
    </PanelSection>
  );

  if (embedded) {
    return (
      <div className="space-y-3">
        <ConsoleSectionNav
          sections={CLOUD_SECTIONS.map((s) => ({ id: s.id, label: s.label }))}
          activeId={activeId}
          onSelect={scrollTo}
          className="!static !z-0 !border-0 !bg-transparent !px-0 !py-0 !backdrop-blur-none"
        />
        {sections}
      </div>
    );
  }

  return (
    <PanelShell scroll={false}>
      <ConsoleSectionNav
        sections={CLOUD_SECTIONS.map((s) => ({ id: s.id, label: s.label }))}
        activeId={activeId}
        onSelect={scrollTo}
      />
      <PanelScroll ref={scrollRef}>{sections}</PanelScroll>
    </PanelShell>
  );
}
