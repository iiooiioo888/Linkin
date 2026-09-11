/**
 * 管線視圖：與角色／任務同一套骨架（標題列、指標帶、三欄、右側資訊）。
 */
import { useMemo } from 'react';
import { buildAnimLiveFeed, mapPhaseToPipelineIndex, pipelinePhaseLabel } from '../lib/animLive';
import {
  PIPELINE_STAGES,
  WORK_ITEM_COLUMNS,
  pipelineStageColumn,
} from '../lib/agentUi';
import { useMonitorStore } from '../stores/monitorStore';
import type { ChatMessage, MultiDimEvaluation } from '../types';
import PipelineDag from './PipelineDag';
import { IterationTrend, ReflectionRadar } from './ReflectionCharts';
import { StatusColumnBoard } from './StatusColumnBoard';
import {
  ConsoleCard,
  ConsoleCardBody,
  ConsoleCardHeader,
  ConsoleRdShell,
  ConsoleRdToolbar,
  KpiCard,
  PanelShell,
  cn,
  consoleLayout,
} from './ui/ConsoleLayout';

interface PipelineViewProps {
  onGoTasks?: () => void;
  messages?: ChatMessage[];
}

export default function PipelineView({ onGoTasks, messages = [] }: PipelineViewProps) {
  const agents = useMonitorStore((s) => s.agents);
  const optimization = useMonitorStore((s) => s.optimization);
  const billing = useMonitorStore((s) => s.billing);
  const llmOps = useMonitorStore((s) => s.llmOps);

  const feed = useMemo(
    () =>
      buildAnimLiveFeed({
        agents,
        optimization,
        billing,
        llmOps,
        messages,
      }),
    [agents, optimization, billing, llmOps, messages],
  );

  // 對話區沒有串流任務時，退回監控快照裡執行中／佇列中的後台任務階段
  const dashboard = useMonitorStore((s) => s.dashboard);
  const backgroundPhase = useMemo(() => {
    const tasks = dashboard?.tasks ?? [];
    const live = tasks.find((t) => t.status === 'running' || t.status === 'pending');
    return live?.phase ?? null;
  }, [dashboard]);

  const phase = feed.streamPhase || feed.taskPhase || backgroundPhase;
  const activeIndex = mapPhaseToPipelineIndex(phase);
  const phaseKnown = !phase || activeIndex != null;
  const currentLabel = phase
    ? pipelinePhaseLabel(phase) ?? phase
    : feed.live
      ? '執行中'
      : '待命';

  const multiDim: MultiDimEvaluation | null = useMemo(() => {
    const dims = optimization?.reflection;
    if (!dims) return null;
    const base = Number(dims.pass_threshold ?? 8);
    return {
      accuracy: { score: base - 0.4, reason: '' },
      completeness: { score: base - 0.6, reason: '' },
      clarity: { score: base - 0.2, reason: '' },
      relevance: { score: base, reason: '' },
      overall: base - 0.3,
      source: 'rule_fallback',
    };
  }, [optimization]);

  const history = useMemo(() => {
    const max = Number(optimization?.reflection?.max_iterations ?? 3);
    return Array.from({ length: max + 1 }, (_, i) => ({
      iteration: i,
      score: Math.min(10, 5.5 + i * 1.1 + (i === max ? 0.4 : 0)),
    }));
  }, [optimization]);

  const stageByCol = useMemo(() => {
    const grouped = { queue: [] as typeof PIPELINE_STAGES[number][], executing: [] as typeof PIPELINE_STAGES[number][], done: [] as typeof PIPELINE_STAGES[number][] };
    PIPELINE_STAGES.forEach((stage, index) => {
      grouped[pipelineStageColumn(index, activeIndex, { phaseKnown })].push(stage);
    });
    return grouped;
  }, [activeIndex, phaseKnown]);

  const kpis = [
    {
      label: '當前',
      value: currentLabel,
      valueClassName: phase || feed.live ? 'console-status-green' : undefined,
    },
    { label: '隊列', value: stageByCol.queue.length },
    { label: '執行中', value: stageByCol.executing.length },
    { label: '已完成', value: stageByCol.done.length, valueClassName: stageByCol.done.length ? 'console-status-green' : undefined },
    { label: '門檻', value: optimization?.reflection?.pass_threshold ?? '—' },
    { label: '路徑', value: feed.resolvedPath || '—', valueClassName: 'truncate text-sm' },
  ];

  return (
    <PanelShell scroll={false}>
      <ConsoleRdShell>
        <ConsoleRdToolbar
          title={`管線 — ${PIPELINE_STAGES.length} 階`}
          actions={
            <button type="button" className="rd-btn" onClick={() => onGoTasks?.()}>
              任務監控
            </button>
          }
        />

        <div className={consoleLayout.kpiStrip6}>
          {kpis.map((kpi) => (
            <KpiCard
              key={kpi.label}
              label={kpi.label}
              value={kpi.value}
              valueClassName={kpi.valueClassName}
            />
          ))}
        </div>

        <div className="rd-body">
          <div className="rd-tasks">
            <StatusColumnBoard
              columns={WORK_ITEM_COLUMNS.map((col) => {
                const stages = stageByCol[col.key];
                return {
                  key: col.key,
                  label: col.label,
                  count: stages.length,
                  children: stages.map((stage) => (
                    <div key={stage.id} className="rd-tc">
                      <div className="rd-tc-t">
                        <span className={`rd-od ${col.key === 'executing' ? 'run' : col.key === 'done' ? 'on' : 'off'}`} />
                        <span className="rd-tc-ttl">{stage.label}</span>
                      </div>
                      <div className="rd-tc-m">
                        <span className={`rd-badge ${col.key === 'executing' ? 'run' : ''}`}>
                          {col.label}
                        </span>
                        <span className="rd-tc-meta">{stage.id}</span>
                      </div>
                    </div>
                  )),
                };
              })}
            />
            <div className="rd-pane">
              <PipelineDag phase={phase} height={260} />
            </div>
          </div>

          <aside
            className={cn(
              'rd-rp flex w-[360px] shrink-0 flex-col overflow-y-auto border-l border-white/[0.06]',
              consoleLayout.sectionStack,
              consoleLayout.cardBody,
            )}
          >
            <ConsoleCard>
              <ConsoleCardHeader>反思雷達</ConsoleCardHeader>
              <ConsoleCardBody dense>
                <ReflectionRadar multiDim={multiDim} />
              </ConsoleCardBody>
            </ConsoleCard>
            <ConsoleCard>
              <ConsoleCardHeader>迭代趨勢</ConsoleCardHeader>
              <ConsoleCardBody dense>
                <IterationTrend history={history} />
              </ConsoleCardBody>
            </ConsoleCard>
          </aside>
        </div>
      </ConsoleRdShell>
    </PanelShell>
  );
}
