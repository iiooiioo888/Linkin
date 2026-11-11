/**
 * 技能與 MCP 面板主殼：技能庫／MCP 連線／可視化插件三分頁。
 *
 * 各分頁內容拆在同套件的 SkillsSection／McpSection／VizPluginsSection。
 */

import { useState } from 'react';
import { PanelSection, PanelShell, consoleLayout } from '../ui/ConsoleLayout';
import { McpSection } from './McpSection';
import { SkillsSection } from './SkillsSection';
import { VizPluginsSection } from './VizPluginsSection';

type SubTab = 'skills' | 'mcp' | 'viz';

export default function SkillsMcpPanel() {
  const [tab, setTab] = useState<SubTab>('skills');
  return (
    <PanelShell constrained>
      <PanelSection>
        <div className={consoleLayout.toolbar}>
          <h2 className={consoleLayout.title}>技能與 MCP</h2>
          <div className="flex gap-1 rounded-xl border border-white/[0.08] bg-[var(--console-card)] p-0.5">
            <button
              type="button"
              className={`rounded-lg px-3 py-1 text-[11px] ${tab === 'skills' ? 'bg-[var(--console-blue)]/15 console-status-blue' : 'text-[var(--console-sub)] hover:text-[var(--console-ink)]'}`}
              onClick={() => setTab('skills')}
            >
              技能庫
            </button>
            <button
              type="button"
              className={`rounded-lg px-3 py-1 text-[11px] ${tab === 'mcp' ? 'bg-[var(--console-blue)]/15 console-status-blue' : 'text-[var(--console-sub)] hover:text-[var(--console-ink)]'}`}
              onClick={() => setTab('mcp')}
            >
              MCP 連線
            </button>
            <button
              type="button"
              className={`rounded-lg px-3 py-1 text-[11px] ${tab === 'viz' ? 'bg-[var(--console-blue)]/15 console-status-blue' : 'text-[var(--console-sub)] hover:text-[var(--console-ink)]'}`}
              onClick={() => setTab('viz')}
              data-testid="skills-tab-viz"
            >
              可視化插件
            </button>
          </div>
        </div>
        {tab === 'skills' ? <SkillsSection /> : null}
        {tab === 'mcp' ? <McpSection /> : null}
        {tab === 'viz' ? <VizPluginsSection /> : null}
      </PanelSection>
    </PanelShell>
  );
}
