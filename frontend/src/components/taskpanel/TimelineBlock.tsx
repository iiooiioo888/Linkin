/**
 * 公司模式事件時間軸（可展開，最近 10 筆）。
 */

import type { Dispatch, SetStateAction } from 'react';
import type { TaskProgress } from '../../types';
import { eventClock } from '../../lib/taskTiming';
import { EVENT_LABELS } from './roleMeta';
import { elapsed } from './time';

export function TimelineBlock({
  task,
  showTimeline,
  setShowTimeline,
}: {
  task: TaskProgress;
  showTimeline: boolean;
  setShowTimeline: Dispatch<SetStateAction<boolean>>;
}) {
  return (
        <div className="mt-2.5">
          <button
            onClick={() => setShowTimeline((v) => !v)}
            className="text-[11px] text-[var(--console-faint)] hover:text-[var(--console-ink)]"
          >
            {showTimeline ? '▲ 收合時間軸' : `▼ 事件時間軸（${task.events.length}）`}
          </button>
          {showTimeline && (
            <div className="task-expand-in relative mt-1.5 ml-1 border-l border-[var(--console-line)]/70 pl-3.5">
              {task.events.slice(-10).map((e, i) => (
                <div key={i} className="relative mb-1 flex items-baseline gap-2 text-[11px] last:mb-0">
                  <span className={`absolute -left-[19px] top-1.5 h-1.5 w-1.5 rounded-full ${
                    e.event === 'work_item_error' ? 'bg-red-400'
                      : e.event === 'work_item_done' || e.event === 'review_pass' || e.event === 'company_done' ? 'bg-green-400'
                        : e.event === 'tool_call' || e.event === 'tool_result' ? 'bg-cyan-400'
                          : 'bg-blue-400/80'
                  }`} />
                  <span className="shrink-0 text-[var(--console-sub)]">{EVENT_LABELS[e.event] ?? e.event}</span>
                  <span className="min-w-0 flex-1 truncate text-[var(--console-faint)]">
                    {e.event === 'tool_call' || e.event === 'tool_result'
                      ? String(e.data.tool ?? '')
                      : String(e.data.title ?? e.data.phase ?? '')}
                  </span>
                  <span className="shrink-0 text-gray-600" title={eventClock(e.ts)}>{elapsed(e.ts)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
  );
}
