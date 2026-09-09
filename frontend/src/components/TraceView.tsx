/** TraceView — 執行軌跡：與任務／角色同一套骨架（指標帶 + 三欄 + 時間線）。 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchTaskTrace } from '../api/client';
import { WORK_ITEM_COLUMNS, fmtWhen, traceEventColumn } from '../lib/agentUi';
import type { TraceEntry } from '../types';
import { StatusColumnBoard } from './StatusColumnBoard';

const EVENT_META: Record<string, { label: string; color: string }> = {
  llm_call: { label: 'LLM 調用', color: 'var(--apple-blue-soft)' },
  context_injection: { label: '上下文注入', color: 'var(--apple-secondary)' },
  evaluation: { label: '評估', color: 'var(--apple-orange)' },
  reflection: { label: '反思', color: '#bf5af2' },
  improvement: { label: '改進', color: 'var(--apple-green)' },
  phase_change: { label: '階段切換', color: 'var(--apple-tertiary)' },
  pipeline_node: { label: '管線節點', color: 'var(--apple-teal, #30b0c7)' },
  tool_call: { label: '工具調用', color: 'var(--apple-orange)' },
  state_snapshot: { label: '狀態快照', color: 'var(--apple-blue-soft)' },
  memory_operation: { label: '記憶操作', color: '#bf5af2' },
  error: { label: '錯誤', color: 'var(--apple-red)' },
};

const NODE_LABELS: Record<string, string> = {
  generate_initial_answer: '生成',
  evaluate_answer: '評估',
  reflect: '反思',
  improve_answer: '改進',
  enforce_output_length: '長度守門',
  decide_final_answer: '最終裁決',
};

const FILTER_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'llm_call', label: 'LLM' },
  { value: 'pipeline_node', label: '節點' },
  { value: 'tool_call', label: '工具' },
  { value: 'evaluation', label: '評估' },
  { value: 'reflection', label: '反思' },
  { value: 'error', label: '錯誤' },
];

function eventSummary(entry: TraceEntry): string {
  if (entry.event === 'llm_call') {
    return `${entry.model ? `[${entry.model}] ` : ''}${String(entry.prompt ?? '').slice(0, 80)}`;
  }
  if (entry.event === 'pipeline_node') {
    const node = String(entry.node ?? '');
    const label = NODE_LABELS[node] || node;
    const bits = [
      entry.score != null ? `分 ${Math.round(Number(entry.score) * 100) / 100}` : '',
      entry.model ? `[${entry.model}]` : '',
      entry.source ? `來源 ${entry.source}` : '',
    ].filter(Boolean);
    return bits.length ? `${label} · ${bits.join(' · ')}` : label;
  }
  if (entry.event === 'evaluation') {
    const score = entry.score != null ? Math.round(Number(entry.score) * 100) / 100 : '—';
    return `分數 ${score} ${String(entry.feedback ?? '').slice(0, 60)}`;
  }
  if (entry.event === 'reflection') return String(entry.reflection ?? '').slice(0, 80);
  if (entry.event === 'context_injection') return `來源 ${entry.source ?? '—'} · ${entry.count ?? 0} 條`;
  if (entry.event === 'tool_call') return `${entry.success ? '✓' : '✗'} ${entry.tool ?? ''}`;
  if (entry.event === 'error') return String(entry.error ?? '').slice(0, 80);
  if (entry.phase) return entry.phase;
  return '';
}

function TraceEventCard({ entry, expanded, onToggle }: { entry: TraceEntry; expanded: boolean; onToggle: () => void }) {
  const meta = EVENT_META[entry.event] ?? { label: entry.event, color: 'var(--apple-tertiary)' };
  const col = traceEventColumn(entry.event);
  const bad = entry.event === 'error' || entry.success === false;
  return (
    <button type="button" onClick={onToggle} className={`rd-tc w-full ${expanded ? 'on' : ''}`}>
      <div className="rd-tc-t">
        <span className={`rd-od ${bad ? 'off' : col === 'executing' ? 'run' : col === 'done' ? 'on' : 'off'}`} />
        <span className="rd-tc-ttl" style={{ color: meta.color }}>{meta.label}</span>
        <span className="rd-tc-id">{fmtWhen(entry.ts)}</span>
      </div>
      <p className="rd-tc-d">{eventSummary(entry) || entry.phase || '—'}</p>
      <div className="rd-tc-m">
        <span className={`rd-badge ${col === 'executing' ? 'run' : ''}`}>
          {entry.phase || (entry.event === 'pipeline_node' ? (NODE_LABELS[String(entry.node ?? '')] || String(entry.node ?? '')) : col)}
        </span>
        {entry.iteration != null && entry.iteration > 0 ? (
          <span className="rd-tc-meta">迭代 {entry.iteration}</span>
        ) : null}
      </div>
      {expanded ? (
        <div className="mt-2 space-y-1.5 border-t border-white/[0.08] pt-2 text-left">
          {entry.system ? (
            <pre className="max-h-24 overflow-auto whitespace-pre-wrap rounded bg-[#141416] px-2 py-1 font-mono text-[10px] text-[#AEAEB2]">
              {entry.system}
            </pre>
          ) : null}
          {entry.prompt ? (
            <pre className="max-h-24 overflow-auto whitespace-pre-wrap rounded bg-[#141416] px-2 py-1 font-mono text-[10px] text-[#AEAEB2]">
              {entry.prompt}
            </pre>
          ) : null}
          {entry.response ? (
            <pre className="max-h-24 overflow-auto whitespace-pre-wrap rounded bg-[#141416] px-2 py-1 font-mono text-[10px] text-[#AEAEB2]">
              {entry.response}
            </pre>
          ) : null}
          {entry.result ? (
            <pre className="max-h-24 overflow-auto whitespace-pre-wrap rounded bg-[#141416] px-2 py-1 font-mono text-[10px] text-[#AEAEB2]">
              {entry.result}
            </pre>
          ) : null}
          {entry.raw_response ? (
            <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded bg-[#141416] px-2 py-1 font-mono text-[10px] text-[#AEAEB2]">
              {entry.raw_response}
            </pre>
          ) : null}
          {entry.items?.length ? (
            <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded bg-[#141416] px-2 py-1 font-mono text-[10px] text-[#AEAEB2]">
              {entry.items.join('\n')}
            </pre>
          ) : null}
          {entry.error ? <p className="text-[11px] text-[#FF453A]">{entry.error}</p> : null}
          {entry.event === 'pipeline_node' ? (
            <p className="font-mono text-[10px] text-[#AEAEB2]">
              {[
                `node=${String(entry.node ?? '')}`,
                entry.model ? `model=${entry.model}` : '',
                entry.score != null ? `score=${entry.score}` : '',
                entry.source ? `source=${entry.source}` : '',
                entry.route ? `route=${entry.route}` : '',
                entry.iteration != null ? `iteration=${entry.iteration}` : '',
              ]
                .filter(Boolean)
                .join('  ')}
            </p>
          ) : null}
        </div>
      ) : null}
    </button>
  );
}

interface TraceViewProps {
  taskId?: string | null;
  onTaskIdChange?: (taskId: string | null) => void;
}

export default function TraceView({ taskId = null, onTaskIdChange }: TraceViewProps) {
  const [error, setError] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(taskId);
  const [events, setEvents] = useState<TraceEntry[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [filter, setFilter] = useState('all');
  const [expanded, setExpanded] = useState<number | null>(null);

  const loadEvents = useCallback(
    async (nextTaskId: string) => {
      setSelectedTaskId(nextTaskId);
      if (nextTaskId !== taskId) onTaskIdChange?.(nextTaskId);
      setEventsLoading(true);
      setEvents([]);
      setError(null);
      try {
        const data = await fetchTaskTrace(nextTaskId, 200, 0);
        setEvents(data.events);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setEventsLoading(false);
      }
    },
    [onTaskIdChange, taskId],
  );

  useEffect(() => {
    if (taskId && taskId !== selectedTaskId) {
      void loadEvents(taskId);
    }
    if (!taskId && selectedTaskId) {
      setSelectedTaskId(null);
      setEvents([]);
    }
  }, [taskId, selectedTaskId, loadEvents]);

  const filteredEvents = filter === 'all' ? events : events.filter((e) => e.event === filter);
  const byCol = useMemo(() => {
    const grouped = { queue: [] as TraceEntry[], executing: [] as TraceEntry[], done: [] as TraceEntry[] };
    for (const entry of filteredEvents) grouped[traceEventColumn(entry.event)].push(entry);
    return grouped;
  }, [filteredEvents]);

  const llmCount = events.filter((e) => e.event === 'llm_call').length;
  const toolCount = events.filter((e) => e.event === 'tool_call').length;
  const errCount = events.filter((e) => e.event === 'error').length;
  const recent = [...filteredEvents].slice(-8).reverse();

  return (
    <div className="rd-shell apple-canvas">
      <div className="rd-th">
        <h2>
          執行軌跡
          {selectedTaskId ? (
            <span className="ml-2 font-mono text-[11px] font-normal text-[var(--apple-blue-soft)]">
              {selectedTaskId.slice(0, 12)}
            </span>
          ) : null}
        </h2>
        {selectedTaskId ? (
          <button
            type="button"
            className="rd-btn"
            onClick={() => {
              setSelectedTaskId(null);
              onTaskIdChange?.(null);
              setEvents([]);
            }}
          >
            清除選取
          </button>
        ) : null}
      </div>

      {error ? (
        <p className="shrink-0 border-b border-red-900/50 bg-red-950/30 px-4 py-2 text-[11px] text-red-400">{error}</p>
      ) : null}

      <div className="rd-stats">
        <div className="rd-stat">
          <span className="rd-stat-l">隊列</span>
          <span className="rd-stat-v">{byCol.queue.length}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">執行中</span>
          <span className="rd-stat-v">{byCol.executing.length}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">已完成</span>
          <span className={`rd-stat-v ${byCol.done.length ? 'ok' : ''}`}>{byCol.done.length}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">LLM</span>
          <span className="rd-stat-v">{llmCount}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">工具</span>
          <span className="rd-stat-v">{toolCount}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">錯誤</span>
          <span className={`rd-stat-v ${errCount ? 'er' : ''}`}>{errCount}</span>
        </div>
      </div>

      <div className="rd-body">
        <div className="rd-tasks">
          <div className="rd-th">
            <h2>
              {selectedTaskId ? `事件 — ${filteredEvents.length}/${events.length}` : '事件'}
            </h2>
            {selectedTaskId ? (
              <div className="rd-ttabs">
                {FILTER_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    className={`rd-ttb ${filter === opt.value ? 'on' : ''}`}
                    onClick={() => setFilter(opt.value)}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-[#636366]">從左側選擇軌跡檔案</p>
            )}
          </div>
          {eventsLoading ? (
            <p className="py-12 text-center text-[11px] text-[#636366]">載入中...</p>
          ) : (
            <StatusColumnBoard
              columns={WORK_ITEM_COLUMNS.map((col) => {
                const rows = byCol[col.key];
                return {
                  key: col.key,
                  label: col.label,
                  count: rows.length,
                  children: rows.map((entry) => (
                    <TraceEventCard
                      key={entry.seq}
                      entry={entry}
                      expanded={expanded === entry.seq}
                      onToggle={() => setExpanded((cur) => (cur === entry.seq ? null : entry.seq))}
                    />
                  )),
                };
              })}
            />
          )}
        </div>

        <aside className="rd-rp">
          <div className="rd-sec">
            <div className="rd-tt">事件時間線</div>
            {recent.length === 0 ? (
              <p className="py-1 text-[11px] text-[#636366]">
                {selectedTaskId ? '尚無事件' : '執行任務後，思考過程會自動記錄在此'}
              </p>
            ) : (
              <div className="rd-ev">
                {recent.map((ev) => {
                  const bad = ev.event === 'error';
                  const meta = EVENT_META[ev.event] ?? { label: ev.event, color: 'var(--apple-tertiary)' };
                  return (
                    <div key={`tl-${ev.seq}`} className="rd-ev-row">
                      <span className={`rd-ev-dot ${bad ? 'er' : 'go'}`} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[10.5px] text-[#AEAEB2]">
                          {meta.label}
                          {eventSummary(ev) ? ` — ${eventSummary(ev)}` : ''}
                        </div>
                        <div className="apple-data text-[8.5px] text-[#636366]">{fmtWhen(ev.ts)}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
