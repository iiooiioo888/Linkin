/**
 * 角色桌面右欄：任務狀態、角色屬性、系統狀態、活動日誌、技能標籤、L0 與快速操作。
 */

import { blankMetrics, fmtWhen } from '../../lib/agentUi';
import { buildRoleStatusStack } from '../../lib/monitorData';
import { agentRahoLabel, orgLevelCaption } from '../../lib/rahoUi';
import type { L0Snapshot, RoleAgent } from '../../types';
import { L0ContextBlock } from '../RoleDeskLayout';
import {
  ConsoleColumnScroll,
  ConsoleRightRail,
  ConsoleSnippetList,
  consoleLayout,
} from '../ui/ConsoleLayout';
import { MiniProgressBar, SkillTags, StackBar } from '../ui/monitor';
import { eventLevel } from './shared';

export function RightRail({ agent, l0 }: { agent: RoleAgent; l0: L0Snapshot | null }) {
  const m = agent.metrics ?? blankMetrics();
  const capPct = Math.round(m.capacity_pct ?? ((agent.capacity_used ?? 0) / Math.max(agent.max_parallel_work, 1)) * 100);
  const statusStack = buildRoleStatusStack(agent);
  const skillTags = [...(agent.tags ?? []), ...(agent.tools_allowed ?? []).slice(0, 6)];
  const quickActions = [
    { label: '任務列表', href: `#/monitor/agents/${encodeURIComponent(agent.id)}` },
    { label: '記憶', href: '#/monitor/memory' },
    { label: '系統總覽', href: '#/monitor/metrics' },
  ];

  return (
      <ConsoleRightRail>
        <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-3">
          <p className="text-[11px] font-semibold text-[var(--console-ink)]">{agent.name}</p>
          <p className="text-[9px] text-[var(--console-faint)]">{orgLevelCaption(agent)}</p>
        </div>
        <ConsoleColumnScroll>
          <div className={consoleLayout.sectionStack}>
            {statusStack.length > 0 ? (
              <ConsoleSnippetList title="任務狀態">
                <div className="px-2 pb-2">
                  <StackBar segments={statusStack} />
                </div>
              </ConsoleSnippetList>
            ) : null}

            <ConsoleSnippetList title="角色屬性">
              <div className="space-y-1 px-2 pb-2 text-[10px]">
                <div className={consoleLayout.snippetRow}>
                  <span>席位</span>
                  <span className="text-[var(--console-accent)]">{agentRahoLabel(agent)}</span>
                </div>
                <div className={consoleLayout.snippetRow}>
                  <span>狀態</span>
                  <span className={agent.enabled === false ? 'text-[var(--console-danger)]' : 'text-[var(--console-green)]'}>
                    {agent.enabled === false ? '停用' : '啟用'}
                  </span>
                </div>
                <div className={consoleLayout.snippetRow}>
                  <span>並行上限</span>
                  <span className="font-mono tabular-nums">{agent.max_parallel_work}</span>
                </div>
                <div className={consoleLayout.snippetRow}>
                  <span>模型層級</span>
                  <span>{agent.default_tier}</span>
                </div>
                <div className={consoleLayout.snippetRow}>
                  <span>工具</span>
                  <span>{agent.tools_allowed?.length ?? 0}</span>
                </div>
              </div>
            </ConsoleSnippetList>

            <ConsoleSnippetList title="系統狀態">
              <div className="space-y-2 px-2 pb-2">
                <div className={consoleLayout.snippetRow}>
                  <span className="inline-flex items-center gap-1.5">
                    <span className={capPct < 80 ? 'apple-dot apple-dot--ok' : 'apple-dot apple-dot--warn'} />
                    容量
                  </span>
                  <span className={capPct < 80 ? 'text-[var(--console-green)]' : 'text-[var(--console-amber)]'}>
                    {capPct}%
                  </span>
                </div>
                <MiniProgressBar value={capPct} hotThreshold={90} good={capPct < 60} />
                <div className={consoleLayout.snippetRow}>
                  <span>Token I/O</span>
                  <span className="font-mono text-[9px]">{m.tokens_in ?? 0} / {m.tokens_out ?? 0}</span>
                </div>
                <MiniProgressBar
                  value={Math.min(100, Math.round(((m.tokens_in ?? 0) + (m.tokens_out ?? 0)) / (agent.context_window || 4096) * 100))}
                />
              </div>
            </ConsoleSnippetList>

            <ConsoleSnippetList title="活動日誌">
              {(agent.events ?? []).length === 0 ? (
                <p className="px-2 py-2 text-[10px] text-[var(--console-faint)]">尚無事件 · 累積中</p>
              ) : (
                <div className="max-h-40 space-y-1 overflow-y-auto px-2 pb-2">
                  {(agent.events ?? []).slice(0, 10).map((ev, i) => {
                    const lv = eventLevel(ev.event);
                    return (
                      <div key={`${ev.ts}-${ev.event}-${i}`} className="flex gap-1.5 text-[10px]">
                        <span
                          className={`shrink-0 rounded px-1 py-0 font-mono text-[8px] uppercase ${
                            lv === 'err'
                              ? 'bg-[color-mix(in_srgb,var(--console-danger)_20%,transparent)] text-[var(--console-danger)]'
                              : lv === 'warn'
                                ? 'bg-[color-mix(in_srgb,var(--console-amber)_20%,transparent)] text-[var(--console-amber)]'
                                : 'bg-[var(--console-card)] text-[var(--console-faint)]'
                          }`}
                        >
                          {lv}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[var(--console-sub)]">{ev.title || ev.event}</p>
                          <p className="text-[8px] text-[var(--console-faint)]">{fmtWhen(ev.ts)}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </ConsoleSnippetList>

            <ConsoleSnippetList title="技能標籤">
              <div className="px-2 pb-2">
                <SkillTags tags={skillTags} />
              </div>
            </ConsoleSnippetList>

            <L0ContextBlock snapshot={l0} />

            <ConsoleSnippetList title="快速操作">
              <div className="grid grid-cols-2 gap-2 p-2">
                {quickActions.map((action) => (
                    <a
                      key={action.label}
                      href={action.href}
                      className="rounded-md border border-[var(--console-line)] bg-[var(--console-card-elevated)] px-2 py-2 text-center text-[10px] font-medium text-[var(--console-sub)] transition-colors hover:border-[color-mix(in_srgb,var(--console-accent)_35%,transparent)] hover:text-[var(--console-ink)]"
                    >
                      {action.label}
                    </a>
                ))}
              </div>
            </ConsoleSnippetList>
          </div>
        </ConsoleColumnScroll>
      </ConsoleRightRail>
  );
}
