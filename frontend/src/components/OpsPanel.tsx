/**
 * 基礎設施合併面板 — 單頁滾動：AI Hub · 雲端 · 檢查點 · 連接池
 */
import { useRef } from 'react';
import CheckpointsPanel from './CheckpointsPanel';
import CloudConsoleView from './CloudConsoleView';
import DbPoolPanel from './DbPoolPanel';
import HubPanel from './HubPanel';
import {
  ConsoleSection,
  ConsoleSectionNav,
  PanelScroll,
  PanelSection,
  PanelShell,
  SectionHeader,
  useScrollToSection,
  useSectionScrollSpy,
  consoleLayout,
} from './ui/ConsoleLayout';

const OPS_SECTIONS = [
  { id: 'ops-hub', label: 'AI Hub' },
  { id: 'ops-cloud', label: '雲端' },
  { id: 'ops-checkpoints', label: '檢查點' },
  { id: 'ops-dbpool', label: '連接池' },
] as const;

export default function OpsPanel() {
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollTo = useScrollToSection(scrollRef);
  const activeId = useSectionScrollSpy(OPS_SECTIONS.map((s) => s.id), scrollRef);

  return (
    <PanelShell scroll={false}>
      <ConsoleSectionNav
        sections={OPS_SECTIONS.map((s) => ({ id: s.id, label: s.label }))}
        activeId={activeId}
        onSelect={(id) => scrollTo(id)}
      />
      <PanelScroll ref={scrollRef}>
        <PanelSection className={consoleLayout.sectionGapLg}>
          <SectionHeader
            title="基礎設施"
            description="AI Hub、雲端運維、斷點續跑與資料庫連接池 — 同一頁連續瀏覽"
          />

          <ConsoleSection id="ops-hub" title="AI Hub" description="模型目錄、探針與熔斷操作台">
            <HubPanel embedded />
          </ConsoleSection>

          <ConsoleSection id="ops-cloud" title="雲端" description="容器監控、實例、告警與事件">
            <CloudConsoleView embedded />
          </ConsoleSection>

          <ConsoleSection id="ops-checkpoints" title="檢查點" description="公司運行時中斷後可從此續跑">
            <CheckpointsPanel embedded />
          </ConsoleSection>

          <ConsoleSection id="ops-dbpool" title="連接池" description="SQLite 連接池狀態與健康檢查">
            <DbPoolPanel embedded />
          </ConsoleSection>
        </PanelSection>
      </PanelScroll>
    </PanelShell>
  );
}
