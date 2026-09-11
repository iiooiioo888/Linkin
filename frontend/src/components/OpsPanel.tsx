/**
 * 基礎設施合併面板 — 分頁切換：AI Hub · 雲端 · 檢查點 · 連接池（無整頁滾動）
 */
import { useState } from 'react';
import CheckpointsPanel from './CheckpointsPanel';
import CloudConsoleView from './CloudConsoleView';
import DbPoolPanel from './DbPoolPanel';
import HubPanel from './HubPanel';
import {
  ConsoleSection,
  ConsoleSectionNav,
  ConsoleTabBody,
  PanelShell,
  SectionHeader,
  consoleLayout,
} from './ui/ConsoleLayout';

const OPS_SECTIONS = [
  { id: 'ops-hub', key: 'hub' as const, label: 'AI Hub' },
  { id: 'ops-cloud', key: 'cloud' as const, label: '雲端' },
  { id: 'ops-checkpoints', key: 'checkpoints' as const, label: '檢查點' },
  { id: 'ops-dbpool', key: 'dbpool' as const, label: '連接池' },
];

type OpsTab = (typeof OPS_SECTIONS)[number]['key'];

export default function OpsPanel() {
  const [tab, setTab] = useState<OpsTab>('hub');
  const activeId = OPS_SECTIONS.find((s) => s.key === tab)?.id ?? OPS_SECTIONS[0].id;

  return (
    <PanelShell scroll={false}>
      <ConsoleSectionNav
        sections={OPS_SECTIONS.map((s) => ({ id: s.id, label: s.label }))}
        activeId={activeId}
        onSelect={(id) => {
          const next = OPS_SECTIONS.find((s) => s.id === id);
          if (next) setTab(next.key);
        }}
      />
      <ConsoleTabBody>
        <SectionHeader
          title="基礎設施"
          description="AI Hub、雲端運維、斷點續跑與資料庫連接池 — 分頁切換，無整頁滾動"
        />
        <div className={consoleLayout.sectionStack + ' min-h-0 flex-1 overflow-hidden'}>
          {tab === 'hub' ? (
            <ConsoleSection id="ops-hub" title="AI Hub" description="模型目錄、探針與熔斷操作台">
              <HubPanel embedded />
            </ConsoleSection>
          ) : null}
          {tab === 'cloud' ? (
            <ConsoleSection id="ops-cloud" title="雲端" description="容器監控、實例、告警與事件">
              <CloudConsoleView embedded />
            </ConsoleSection>
          ) : null}
          {tab === 'checkpoints' ? (
            <ConsoleSection id="ops-checkpoints" title="檢查點" description="公司運行時中斷後可從此續跑">
              <CheckpointsPanel embedded />
            </ConsoleSection>
          ) : null}
          {tab === 'dbpool' ? (
            <ConsoleSection id="ops-dbpool" title="連接池" description="SQLite 連接池狀態與健康檢查">
              <DbPoolPanel embedded />
            </ConsoleSection>
          ) : null}
        </div>
      </ConsoleTabBody>
    </PanelShell>
  );
}
