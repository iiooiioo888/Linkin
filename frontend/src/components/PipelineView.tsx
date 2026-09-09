/**
 * 管線視圖：與角色／任務同一套骨架（標題列、指標帶、三欄、右側資訊）。
 */
import { useMemo } from 'react';
import { buildAnimLiveFeed, mapPhaseToPipelineIndex } from '../lib/animLive';
import {
  PIPELINE_STAGES,
  WORK_ITEM_COLUMNS,
  pipelineStageColumn,
} from '../lib/agentUi';
import { useMonitorStore } from '../stores/monitorStore';
import type { MultiDimEvaluation } from '../types';
import PipelineDag from './PipelineDag';
import { IterationTrend, ReflectionRadar } from './ReflectionCharts';
import { StatusColumnBoard } from './StatusColumnBoard';

interface PipelineViewProps {
  onGoTasks?: () => void;
}

export default function PipelineView({ onGoTasks }: PipelineViewProps) {
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
      }),
    [agents, optimization, billing, llmOps],
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
  const currentLabel =
    activeIndex != null ? PIPELINE_STAGES[activeIndex]?.label : '待命';

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
      grouped[pipelineStageColumn(index, activeIndex)].push(stage);
    });
    return grouped;
  }, [activeIndex]);

  return (
    <div className="rd-shell apple-canvas">
      <div className="rd-th">
        <h2>管線 — {PIPELINE_STAGES.length} 階</h2>
        <button type="button" className="rd-btn" onClick={() => onGoTasks?.()}>
          任務監控
        </button>
      </div>

      <div className="rd-stats">
        <div className="rd-stat">
          <span className="rd-stat-l">當前</span>
          <span className={`rd-stat-v ${activeIndex != null ? 'ok' : ''}`}>{currentLabel}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">隊列</span>
          <span className="rd-stat-v">{stageByCol.queue.length}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">執行中</span>
          <span className="rd-stat-v">{stageByCol.executing.length}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">已完成</span>
          <span className={`rd-stat-v ${stageByCol.done.length ? 'ok' : ''}`}>{stageByCol.done.length}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">門檻</span>
          <span className="rd-stat-v">{optimization?.reflection?.pass_threshold ?? '—'}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">路徑</span>
          <span className="rd-stat-v">{feed.resolvedPath || '—'}</span>
        </div>
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

        <aside className="rd-rp">
          <div className="rd-sec">
            <div className="rd-tt">反思雷達</div>
            <ReflectionRadar multiDim={multiDim} />
          </div>
          <div className="rd-sec">
            <div className="rd-tt">迭代趨勢</div>
            <IterationTrend history={history} />
          </div>
        </aside>
      </div>
    </div>
  );
}
