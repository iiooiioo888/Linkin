/**
 * 角色桌面左欄：角色切換、區塊導覽、角色名冊、活動熱力圖與資源。
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { blankMetrics } from '../../lib/agentUi';
import {
  agentResourceGauges,
  buildActivityHeatmap,
  roleWorkItemsAsTasks,
} from '../../lib/monitorData';
import { agentRahoLabel } from '../../lib/rahoUi';
import type { RoleAgent } from '../../types';
import { roleInitials } from '../RoleDeskLayout';
import {
  ConsoleCard,
  ConsoleCardHeader,
  ConsoleColumnScroll,
  ConsoleLeftRail,
  ConsoleRailNav,
} from '../ui/ConsoleLayout';
import { ActivityHeatmap, ResourceGauges } from '../ui/monitor';
import { LEFT_SECTIONS, isLive } from './shared';

export function LeftRail({
  agent,
  agents,
  isMobileLite,
  showDenseWidgets,
  activeSection,
  scrollTo,
  onSelectAgent,
}: {
  agent: RoleAgent;
  agents: RoleAgent[];
  isMobileLite: boolean;
  showDenseWidgets: boolean;
  activeSection: string | undefined;
  scrollTo: (id: string) => void;
  onSelectAgent: (id: string) => void;
}) {
  const { t } = useTranslation();
  const m = agent.metrics ?? blankMetrics();
  const budgetWarn = agent.budget_over || agent.ai_budget_over || agent.cloud_budget_over || (m.budget_alerts ?? 0) > 0;

  const groupedAgents = useMemo(() => {
    const groups = new Map<string, RoleAgent[]>();
    for (const a of agents) {
      const key = a.raho_short || a.level_label || `L${a.level}`;
      const list = groups.get(key) ?? [];
      list.push(a);
      groups.set(key, list);
    }
    return [...groups.entries()].sort((a, b) => {
      const la = a[1][0]?.raho_layer ?? a[1][0]?.level ?? 99;
      const lb = b[1][0]?.raho_layer ?? b[1][0]?.level ?? 99;
      return lb - la;
    });
  }, [agents]);

  const roleTasks = roleWorkItemsAsTasks(agent);
  const heatmap = buildActivityHeatmap(roleTasks, agent.events ?? []);
  const heatmapEmpty = heatmap.every((r) => r.every((c) => c.level === 0 && !c.error));

  return (
      <ConsoleLeftRail>
        <div className="shrink-0 border-b border-[var(--console-line)] px-3 py-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--console-accent)_18%,transparent)] text-[11px] font-semibold text-[var(--console-accent)]">
              {roleInitials(agent.name)}
            </div>
            <div className="min-w-0">
              <p className="truncate text-[12px] font-semibold text-[var(--console-ink)]">{agent.name}</p>
              <p className="truncate text-[9px] text-[var(--console-faint)]">{agentRahoLabel(agent)}</p>
            </div>
          </div>
        </div>

        <ConsoleColumnScroll className="!px-0 !py-0">
          <ConsoleRailNav
            sections={LEFT_SECTIONS}
            activeId={activeSection}
            onSelect={scrollTo}
            header={
              <p className="px-3 pb-1 pt-2 text-[9px] font-semibold text-[var(--console-faint)]">
                區塊
              </p>
            }
          />

          <div className="space-y-3 px-3 py-3">
            <div>
              <p className="mb-1.5 text-[9px] font-semibold text-[var(--console-faint)]">
                角色名冊
              </p>
              <div className="max-h-36 space-y-2 overflow-y-auto console-col-scroll">
                {groupedAgents.map(([group, list]) => (
                  <div key={group}>
                    <p className="mb-0.5 text-[8px] font-semibold text-[var(--console-faint)]">
                      {group}
                    </p>
                    {list.map((a) => (
                      <button
                        key={a.id}
                        type="button"
                        onClick={() => onSelectAgent(a.id)}
                        className={`mb-0.5 flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-[10px] transition-colors ${
                          a.id === agent.id
                            ? 'bg-[color-mix(in_srgb,var(--console-accent)_12%,transparent)] text-[var(--console-ink)]'
                            : 'text-[var(--console-sub)] hover:bg-[var(--console-card)] hover:text-[var(--console-ink)]'
                        }`}
                      >
                        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${isLive(a) ? 'bg-[var(--console-green)]' : 'bg-[var(--console-dim)]'}`} />
                        <span className="truncate">{a.name}</span>
                        {a.executing > 0 ? (
                          <span className="ml-auto shrink-0 font-mono text-[9px] text-[var(--console-blue)]">{a.executing}</span>
                        ) : null}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            </div>

            {(!isMobileLite || showDenseWidgets) && (
              <ConsoleCard>
                <ConsoleCardHeader>活動熱力圖</ConsoleCardHeader>
                <div className="p-2">
                  <ActivityHeatmap rows={heatmap} demo={heatmapEmpty} title="7×24" />
                </div>
              </ConsoleCard>
            )}

            <ConsoleCard>
              <ConsoleCardHeader>資源</ConsoleCardHeader>
              <div className="p-2">
                <ResourceGauges gauges={agentResourceGauges(agent)} size={40} />
              </div>
            </ConsoleCard>

            <div className="flex flex-wrap gap-1">
              <span className={`rounded px-1.5 py-0.5 text-[9px] ${agent.status === 'busy' ? 'bg-[color-mix(in_srgb,var(--console-green)_15%,transparent)] text-[var(--console-green)]' : 'bg-[var(--console-card)] text-[var(--console-faint)]'}`}>
                {agent.status === 'busy' ? '執行中' : agent.status === 'waiting' ? '等待' : '待命'}
              </span>
              {agent.on_call ? <span className="rounded bg-[var(--console-card)] px-1.5 py-0.5 text-[9px] text-[var(--console-accent)]">值班</span> : null}
              {budgetWarn ? (
                <span className="rounded bg-[color-mix(in_srgb,var(--console-amber)_15%,transparent)] px-1.5 py-0.5 text-[9px] text-[var(--console-amber)]">
                  {(m.budget_alerts ?? 0) > 0 ? t('roles.budgetAlertShort', { count: m.budget_alerts }) : t('roles.budgetOver')}
                </span>
              ) : null}
            </div>
          </div>
        </ConsoleColumnScroll>
      </ConsoleLeftRail>
  );
}
