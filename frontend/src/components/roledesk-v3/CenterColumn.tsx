/**
 * 角色桌面中欄：容量警告、預算摘要、KPI、任務分佈／管線／看板與組織回報鏈。
 */

import { useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { blankMetrics, itemsInColumn, type WorkItemColumnKey } from '../../lib/agentUi';
import {
  buildAgentSparkSeries,
  buildRolePipelineNodes,
  buildRoleStatusStack,
  buildTaskDistributionMatrix,
  roleWorkItemsAsTasks,
} from '../../lib/monitorData';
import type { RoleAgent } from '../../types';
import { OrgReportTree } from '../RoleDeskLayout';
import { RoleBudgetSummary } from '../RoleBudgetSummary';
import { StatusColumnBoard } from '../StatusColumnBoard';
import {
  ConsoleCard,
  ConsoleCardHeader,
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  KpiGrid6,
  WarnBar,
  consoleLayout,
} from '../ui/ConsoleLayout';
import {
  KpiSparkCard,
  PipelineTimeline,
  StackBar,
  TaskDistributionMatrix,
} from '../ui/monitor';
import { KANBAN_COLUMNS } from './shared';
import { WorkKanbanCard } from './WorkKanbanCard';

export function CenterColumn({
  agent,
  agents,
  isMobileLite,
  showDenseWidgets,
  setShowDenseWidgets,
  scrollRef,
  onSelectAgent,
}: {
  agent: RoleAgent;
  agents: RoleAgent[];
  isMobileLite: boolean;
  showDenseWidgets: boolean;
  setShowDenseWidgets: (value: boolean) => void;
  scrollRef: RefObject<HTMLDivElement | null>;
  onSelectAgent: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [itemFilter, setItemFilter] = useState<WorkItemColumnKey>('executing');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const m = agent.metrics ?? blankMetrics();
  const capPct = Math.round(m.capacity_pct ?? ((agent.capacity_used ?? 0) / Math.max(agent.max_parallel_work, 1)) * 100);
  const success = m.success_rate ?? 0;
  const spark = buildAgentSparkSeries(agent);
  const roleTasks = roleWorkItemsAsTasks(agent);
  const taskMatrix = buildTaskDistributionMatrix(roleTasks);
  const matrixEmpty = taskMatrix.every((r) => r.every((c) => c.count === 0));
  const pipelineNodes = buildRolePipelineNodes(agent);
  const statusStack = buildRoleStatusStack(agent);
  const budgetWarn = agent.budget_over || agent.ai_budget_over || agent.cloud_budget_over || (m.budget_alerts ?? 0) > 0;
  const capacityWarn = capPct >= 80 || budgetWarn;

  return (
      <ConsoleCenterColumn>
        <ConsoleColumnScroll ref={scrollRef}>
          {capacityWarn ? (
            <WarnBar className="mb-3">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--console-amber)]" />
              {capPct >= 80 ? `並行容量 ${capPct}%（${agent.executing}/${agent.max_parallel_work}）` : null}
              {budgetWarn ? ` · ${(m.budget_alerts ?? 0) > 0 ? t('roles.budgetAlertShort', { count: m.budget_alerts }) : t('roles.budgetOver')}` : null}
            </WarnBar>
          ) : null}

          <section id="role-overview" className={consoleLayout.sectionAnchor}>
            <div className="mb-3">
              <RoleBudgetSummary agent={agent} compact={isMobileLite} />
            </div>
            {(!isMobileLite || showDenseWidgets) ? (
              <KpiGrid6 className="mb-3">
                {[
                  { label: '成功率', value: success > 0 ? `${success}%` : '—', accent: true },
                  { label: '延遲', value: `${Math.round(m.avg_latency_ms ?? 0)}`, unit: 'ms' },
                  { label: '執行中', value: String(agent.executing) },
                  { label: '序列', value: String(agent.queue) },
                  { label: 'P95', value: `${Math.round(m.p95_latency_ms ?? 0)}`, unit: 'ms' },
                  { label: 'SLA 違規', value: String(m.sla_breaches ?? 0) },
                ].map((kpi) => (
                  <KpiSparkCard
                    key={kpi.label}
                    label={kpi.label}
                    value={kpi.value}
                    unit={kpi.unit}
                    spark={spark}
                    accent={kpi.accent}
                  />
                ))}
              </KpiGrid6>
            ) : (
              <div className="mb-3 grid grid-cols-3 gap-2">
                <KpiSparkCard label="執行中" value={String(agent.executing)} spark={spark} accent />
                <KpiSparkCard label="序列" value={String(agent.queue)} spark={spark} />
                <KpiSparkCard label="成功率" value={success > 0 ? `${success}%` : '—'} spark={spark} />
              </div>
            )}
          </section>

          <section id="role-execution" className={`${consoleLayout.sectionAnchor} space-y-3`}>
            {isMobileLite && !showDenseWidgets ? (
              <button
                type="button"
                onClick={() => setShowDenseWidgets(true)}
                className="w-full rounded-lg border border-[var(--console-line)] bg-[var(--console-card)] px-3 py-2 text-[11px] text-[var(--console-sub)] hover:text-[var(--console-ink)]"
              >
                {t('roles.showDenseWidgets')}
              </button>
            ) : (
              <ConsoleCard>
                <ConsoleCardHeader>任務分佈 · L4/L3/L2 × 24h</ConsoleCardHeader>
                <div className="p-3">
                  <TaskDistributionMatrix matrix={taskMatrix} demo={matrixEmpty} />
                </div>
              </ConsoleCard>
            )}

            <ConsoleCard>
              <ConsoleCardHeader>任務管線 · 節點耗時</ConsoleCardHeader>
              <div className="p-3">
                <PipelineTimeline nodes={pipelineNodes} />
              </div>
            </ConsoleCard>

            {statusStack.length > 0 ? (
              <div className="rounded-lg border border-[var(--console-line)] bg-[var(--console-card)] px-3 py-2">
                <p className="mb-1.5 text-[9px] font-semibold text-[var(--console-faint)]">工作項狀態</p>
                <StackBar segments={statusStack} />
              </div>
            ) : null}

            <div>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-[10px] font-semibold text-[var(--console-faint)]">
                  看板 · 待辦 / 進行中 / 已完成
                </h3>
                <span className="text-[9px] text-[var(--console-faint)]">{agent.work_items.length} 項</span>
              </div>
              <StatusColumnBoard
                compact
                selectedKey={itemFilter}
                onSelect={(key) => setItemFilter(key as WorkItemColumnKey)}
                columns={KANBAN_COLUMNS.map((col) => {
                  const items = itemsInColumn(agent.work_items, col.key);
                  return {
                    key: col.key,
                    label: col.label,
                    count: items.length,
                    children: items.length === 0 ? (
                      <p className="py-4 text-center text-[10px] text-[var(--console-faint)]">累積中</p>
                    ) : (
                      items.map((item) => (
                        <WorkKanbanCard
                          key={`${item.task_id}-${item.id}-${item.kind}`}
                          item={item}
                          expanded={expandedId === `${item.task_id}-${item.id}-${item.kind}`}
                          onToggle={() =>
                            setExpandedId((cur) => {
                              const key = `${item.task_id}-${item.id}-${item.kind}`;
                              return cur === key ? null : key;
                            })
                          }
                        />
                      ))
                    ),
                  };
                })}
              />
            </div>
          </section>

          <section id="role-system" className={`${consoleLayout.sectionAnchor} mt-3 pb-4`}>
            <ConsoleCard>
              <ConsoleCardHeader>組織回報鏈</ConsoleCardHeader>
              <div className="p-3">
                <OrgReportTree agent={agent} agents={agents} onOpen={onSelectAgent} />
              </div>
            </ConsoleCard>
          </section>
        </ConsoleColumnScroll>
      </ConsoleCenterColumn>
  );
}
