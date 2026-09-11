/**
 * 基礎設施合併面板 — OCD 三欄：左導航 · 中主面板 · 右快操
 */
import { useState } from 'react';
import CheckpointsPanel from './CheckpointsPanel';
import CloudConsoleView from './CloudConsoleView';
import DbPoolPanel from './DbPoolPanel';
import HubPanel from './HubPanel';
import {
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  ConsoleLeftRail,
  ConsoleRailNav,
  ConsoleRightRail,
  ConsoleSnippetList,
  ConsoleThreeColumn,
  PanelShell,
  consoleLayout,
} from './ui/ConsoleLayout';

const OPS_SECTIONS = [
  { id: 'ops-hub', key: 'hub' as const, label: 'AI Hub' },
  { id: 'ops-cloud', key: 'cloud' as const, label: '雲端' },
  { id: 'ops-checkpoints', key: 'checkpoints' as const, label: '檢查點' },
  { id: 'ops-dbpool', key: 'dbpool' as const, label: '連接池' },
];

type OpsTab = (typeof OPS_SECTIONS)[number]['key'];

const OPS_HINTS: Record<OpsTab, string> = {
  hub: '模型目錄、探針與熔斷',
  cloud: '容器監控、實例、告警',
  checkpoints: '中斷後從檢查點續跑',
  dbpool: 'SQLite 連接池健康',
};

export default function OpsPanel() {
  const [tab, setTab] = useState<OpsTab>('hub');
  const activeId = OPS_SECTIONS.find((s) => s.key === tab)?.id ?? OPS_SECTIONS[0].id;

  return (
    <PanelShell scroll={false}>
      <ConsoleThreeColumn>
        <ConsoleLeftRail>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-4">
            <h1 className="text-[15px] font-semibold text-[var(--console-ink)]">基礎設施</h1>
            <p className="mt-1 text-[10px] text-[var(--console-faint)]">Hub · 雲端 · 檢查點 · 連接池</p>
          </div>
          <ConsoleColumnScroll className="!px-0 !py-0">
            <ConsoleRailNav
              sections={OPS_SECTIONS.map((s) => ({ id: s.id, label: s.label }))}
              activeId={activeId}
              onSelect={(id) => {
                const next = OPS_SECTIONS.find((s) => s.id === id);
                if (next) setTab(next.key);
              }}
            />
          </ConsoleColumnScroll>
        </ConsoleLeftRail>

        <ConsoleCenterColumn>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-3">
            <p className="text-[13px] font-semibold text-[var(--console-ink)]">
              {OPS_SECTIONS.find((s) => s.key === tab)?.label}
            </p>
            <p className="text-[10px] text-[var(--console-faint)]">{OPS_HINTS[tab]}</p>
          </div>
          <ConsoleColumnScroll>
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              {tab === 'hub' ? <HubPanel embedded /> : null}
              {tab === 'cloud' ? <CloudConsoleView embedded /> : null}
              {tab === 'checkpoints' ? <CheckpointsPanel embedded /> : null}
              {tab === 'dbpool' ? <DbPoolPanel embedded /> : null}
            </div>
          </ConsoleColumnScroll>
        </ConsoleCenterColumn>

        <ConsoleRightRail>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-3">
            <p className="text-[11px] font-semibold text-[var(--console-ink)]">運維快操</p>
          </div>
          <ConsoleColumnScroll>
            <div className={consoleLayout.sectionStack}>
              <ConsoleSnippetList title="目前區塊">
                <p className="text-[11px] text-[var(--console-sub)]">{OPS_HINTS[tab]}</p>
              </ConsoleSnippetList>
              {tab === 'cloud' ? (
                <ConsoleSnippetList title="計費整合">
                  <p className="text-[11px] text-[var(--console-sub)]">
                    雲費用帳單已整合至靈境積分中心 → 雲與 Docker
                  </p>
                </ConsoleSnippetList>
              ) : null}
              <ConsoleSnippetList title="提示">
                <div className={consoleLayout.snippetRow}>
                  <span>整頁滾動</span>
                  <span className="console-status-green">已禁用</span>
                </div>
                <div className={consoleLayout.snippetRow}>
                  <span>欄內滾動</span>
                  <span className="text-[var(--console-sub)]">4px</span>
                </div>
              </ConsoleSnippetList>
            </div>
          </ConsoleColumnScroll>
        </ConsoleRightRail>
      </ConsoleThreeColumn>
    </PanelShell>
  );
}
