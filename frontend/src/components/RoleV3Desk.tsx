/**
 * RoleV3Desk — 角色監控三欄桌面（216 / 1fr / 304）。
 * 對齊 docs/design/monitor-dashboard-v3.html 與 SystemMetricsPanel 結構。
 */
import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useIsMobileLiteShell } from '../hooks/useMediaQuery';
import type { AgentWorkItem, GrillTreeNode, L0Snapshot, RahoSnapshot, RoleAgent } from '../types';
import {
  blankMetrics,
  fmtUsd,
  fmtWhen,
  itemsInColumn,
  type WorkItemColumnKey,
} from '../lib/agentUi';
import {
  agentRahoLabel,
  orgLevelCaption,
} from '../lib/rahoUi';
import {
  agentResourceGauges,
  buildActivityHeatmap,
  buildAgentSparkSeries,
  buildRolePipelineNodes,
  buildRoleStatusStack,
  buildTaskDistributionMatrix,
  roleWorkItemsAsTasks,
  workItemPriority,
} from '../lib/monitorData';
import { ITEM_STATUS_META } from './TaskPanel';
import GrillTreePanel from './GrillTreePanel';
import { StatusColumnBoard } from './StatusColumnBoard';
import {
  ActivityHeatmap,
  KpiSparkCard,
  MiniProgressBar,
  PipelineTimeline,
  ResourceGauges,
  SkillTags,
  StackBar,
  TaskDistributionMatrix,
  TaskPriorityCard,
} from './ui/monitor';
import {
  ConsoleCard,
  ConsoleCardHeader,
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  ConsoleLeftRail,
  ConsoleRailNav,
  ConsoleRightRail,
  ConsoleSnippetList,
  ConsoleThreeColumn,
  KpiGrid6,
  WarnBar,
  consoleLayout,
  useScrollToSection,
  useSectionScrollSpy,
} from './ui/ConsoleLayout';
import {
  L0ContextBlock,
  OrgReportTree,
  RahoChainBlock,
  roleInitials,
} from './RoleDeskLayout';

const KANBAN_COLUMNS = [
  { key: 'queue' as WorkItemColumnKey, label: '待辦' },
  { key: 'executing' as WorkItemColumnKey, label: '進行中' },
  { key: 'done' as WorkItemColumnKey, label: '已完成' },
];

const LEFT_SECTIONS = [
  { id: 'role-overview', label: '概覽' },
  { id: 'role-execution', label: '執行' },
  { id: 'role-grill', label: '角色' },
  { id: 'role-system', label: '系統' },
];

function isLive(agent: RoleAgent): boolean {
  return agent.status === 'busy' || agent.status === 'waiting';
}

function eventLevel(event: string): 'info' | 'warn' | 'err' {
  if (event.includes('error') || event.includes('fail')) return 'err';
  if (event.includes('warn') || event.includes('block')) return 'warn';
  return 'info';
}

function WorkKanbanCard({
  item,
  expanded,
  onToggle,
}: {
  item: AgentWorkItem;
  expanded?: boolean;
  onToggle?: () => void;
}) {
  const st = ITEM_STATUS_META[item.status] ?? { label: item.status, cls: '' };
  const shortId = (item.task_id || item.id || '').replace(/^.*[#-]/, '').slice(-4) || item.id.slice(0, 4);
  const priority = workItemPriority(item);
  return (
    <TaskPriorityCard
      priority={priority}
      title={item.title}
      active={expanded}
      onClick={onToggle}
      meta={
        <>
          <span>{st.label}</span>
          <span>#{shortId}</span>
          <span>{fmtWhen(item.updated_at)}</span>
          <span>{fmtUsd(item.cost_usd)}</span>
        </>
      }
    >
      {expanded ? (
        <div className="mt-1 space-y-1 border-t border-[var(--console-line)] pt-1.5">
          {item.description ? (
            <p className="text-[10px] leading-relaxed text-[var(--console-sub)]">{item.description}</p>
          ) : null}
          {item.output_preview ? (
            <pre className="max-h-24 overflow-auto whitespace-pre-wrap rounded bg-[var(--console-bg)] px-2 py-1 font-mono text-[9px] text-[var(--console-sub)]">
              {item.output_preview}
            </pre>
          ) : null}
        </div>
      ) : null}
    </TaskPriorityCard>
  );
}

export interface RoleV3DeskProps {
  agent: RoleAgent;
  agents: RoleAgent[];
  rahoSnap: RahoSnapshot | null;
  grillNodes: GrillTreeNode[];
  l0: L0Snapshot | null;
  onSelectAgent: (id: string) => void;
  onOpenGrill: () => void;
}

export default function RoleV3Desk({
  agent,
  agents,
  rahoSnap,
  grillNodes: _grillNodes,
  l0,
  onSelectAgent,
  onOpenGrill,
}: RoleV3DeskProps) {
  const { t } = useTranslation();
  const isMobileLite = useIsMobileLiteShell();
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollTo = useScrollToSection(scrollRef);
  const activeSection = useSectionScrollSpy(LEFT_SECTIONS.map((s) => s.id), scrollRef);
  const [itemFilter, setItemFilter] = useState<WorkItemColumnKey>('executing');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showDenseWidgets, setShowDenseWidgets] = useState(false);

  const m = agent.metrics ?? blankMetrics();
  const capPct = Math.round(m.capacity_pct ?? ((agent.capacity_used ?? 0) / Math.max(agent.max_parallel_work, 1)) * 100);
  const success = m.success_rate ?? 0;
  const spark = buildAgentSparkSeries(agent);
  const roleTasks = roleWorkItemsAsTasks(agent);
  const heatmap = buildActivityHeatmap(roleTasks, agent.events ?? []);
  const heatmapEmpty = heatmap.every((r) => r.every((c) => c.level === 0 && !c.error));
  const taskMatrix = buildTaskDistributionMatrix(roleTasks);
  const matrixEmpty = taskMatrix.every((r) => r.every((c) => c.count === 0));
  const statusStack = buildRoleStatusStack(agent);
  const pipelineNodes = buildRolePipelineNodes(agent);
  const skillTags = [...(agent.tags ?? []), ...(agent.tools_allowed ?? []).slice(0, 6)];
  const capacityWarn = capPct >= 80 || (m.budget_alerts ?? 0) > 0;

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

  const quickActions = [
    { label: '質詢樹', onClick: onOpenGrill },
    { label: '任務列表', href: `#/monitor/agents/${encodeURIComponent(agent.id)}` },
    { label: 'L0 核心', href: '#/monitor/memory' },
    { label: '系統總覽', href: '#/monitor/metrics' },
  ];

  return (
    <ConsoleThreeColumn
      className="min-h-0 flex-1"
      liteShell={isMobileLite}
      mobileLabels={{ left: '導覽', center: '監控', right: '詳情' }}
    >
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
              <p className="px-3 pb-1 pt-2 text-[9px] font-semibold uppercase tracking-wider text-[var(--console-faint)]">
                區塊
              </p>
            }
          />

          <div className="space-y-3 px-3 py-3">
            <div>
              <p className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-[var(--console-faint)]">
                角色名冊
              </p>
              <div className="max-h-36 space-y-2 overflow-y-auto console-col-scroll">
                {groupedAgents.map(([group, list]) => (
                  <div key={group}>
                    <p className="mb-0.5 text-[8px] font-semibold uppercase tracking-wider text-[var(--console-faint)]">
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
              {(m.budget_alerts ?? 0) > 0 ? (
                <span className="rounded bg-[color-mix(in_srgb,var(--console-amber)_15%,transparent)] px-1.5 py-0.5 text-[9px] text-[var(--console-amber)]">
                  告警 {m.budget_alerts}
                </span>
              ) : null}
            </div>
          </div>
        </ConsoleColumnScroll>
      </ConsoleLeftRail>

      <ConsoleCenterColumn>
        <ConsoleColumnScroll ref={scrollRef}>
          {capacityWarn ? (
            <WarnBar className="mb-3">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--console-amber)]" />
              {capPct >= 80 ? `並行容量 ${capPct}%（${agent.executing}/${agent.max_parallel_work}）` : null}
              {(m.budget_alerts ?? 0) > 0 ? ` · 預算告警 ${m.budget_alerts}` : null}
            </WarnBar>
          ) : null}

          <section id="role-overview" className={consoleLayout.sectionAnchor}>
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
              <ConsoleCardHeader>指揮鏈管線 · 節點耗時</ConsoleCardHeader>
              <div className="p-3">
                <PipelineTimeline nodes={pipelineNodes} />
              </div>
            </ConsoleCard>

            {statusStack.length > 0 ? (
              <div className="rounded-lg border border-[var(--console-line)] bg-[var(--console-card)] px-3 py-2">
                <p className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-[var(--console-faint)]">工作項狀態</p>
                <StackBar segments={statusStack} />
              </div>
            ) : null}

            <div>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-[10px] font-semibold uppercase tracking-wider text-[var(--console-faint)]">
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

          <section id="role-grill" className={`${consoleLayout.sectionAnchor} mt-3`}>
            <ConsoleCard>
              <ConsoleCardHeader>質詢鏈</ConsoleCardHeader>
              <div className="p-2">
                <GrillTreePanel
                  embedded
                  compact
                  disablePoll
                  snap={rahoSnap}
                  focusRoleId={agent.id}
                  onSelectRole={(id) => onSelectAgent(id)}
                />
              </div>
            </ConsoleCard>
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
                  <span>RAHO</span>
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

            <RahoChainBlock agent={agent} onOpenGrill={onOpenGrill} />
            <L0ContextBlock snapshot={l0} />

            <ConsoleSnippetList title="快速操作">
              <div className="grid grid-cols-2 gap-2 p-2">
                {quickActions.map((action) =>
                  action.href ? (
                    <a
                      key={action.label}
                      href={action.href}
                      className="rounded-md border border-[var(--console-line)] bg-[var(--console-card-elevated)] px-2 py-2 text-center text-[10px] font-medium text-[var(--console-sub)] transition-colors hover:border-[color-mix(in_srgb,var(--console-accent)_35%,transparent)] hover:text-[var(--console-ink)]"
                    >
                      {action.label}
                    </a>
                  ) : (
                    <button
                      key={action.label}
                      type="button"
                      onClick={action.onClick}
                      className="rounded-md border border-[var(--console-line)] bg-[var(--console-card-elevated)] px-2 py-2 text-center text-[10px] font-medium text-[var(--console-sub)] transition-colors hover:border-[color-mix(in_srgb,var(--console-accent)_35%,transparent)] hover:text-[var(--console-ink)]"
                    >
                      {action.label}
                    </button>
                  ),
                )}
              </div>
            </ConsoleSnippetList>
          </div>
        </ConsoleColumnScroll>
      </ConsoleRightRail>
    </ConsoleThreeColumn>
  );
}
