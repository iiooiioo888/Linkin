/**
 * SidePanel 任務列表（虛擬滾動＋分欄折疊）。
 */
import { useEffect, useMemo, useState } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { Virtuoso } from 'react-virtuoso';
import { taskColumnKey, tasksInColumn, TASK_COLUMNS, type TaskColumnKey } from '../../lib/agentUi';
import { useMonitorStore } from '../../stores/monitorStore';
import type { TaskSummary } from '../../types';

const TASK_STATUS_DOT: Record<string, string> = {
  pending: 'bg-[var(--console-amber)]',
  running: 'bg-[var(--console-accent)] animate-pulse',
  completed: 'bg-[var(--console-green)]',
  failed: 'bg-[var(--console-danger)]',
  cancelled: 'bg-[var(--console-sub)]',
  interrupted: 'bg-[var(--console-amber)]',
};

const EMPTY_TASKS: TaskSummary[] = [];

const selectTaskRoster = (s: ReturnType<typeof useMonitorStore.getState>) =>
  s.dashboard?.tasks ?? EMPTY_TASKS;

type TaskRosterRow =
  | { kind: 'header'; key: TaskColumnKey; label: string; count: number }
  | { kind: 'task'; key: string; task: TaskSummary };

export function TaskRoster({
  focusTaskId,
  onPick,
}: {
  focusTaskId: string | null;
  onPick: (id: string) => void;
}) {
  const tasks = useMonitorStore(useShallow(selectTaskRoster));
  const [query, setQuery] = useState('');
  const [openCols, setOpenCols] = useState<Set<TaskColumnKey>>(() => new Set(['queue', 'running', 'done', 'failed']));

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q
      ? tasks.filter((t) => t.query.toLowerCase().includes(q) || t.task_id.includes(q))
      : tasks;
    return list.slice(0, 80);
  }, [tasks, query]);

  const rows: TaskRosterRow[] = useMemo(() => {
    const out: TaskRosterRow[] = [];
    for (const col of TASK_COLUMNS) {
      const list = tasksInColumn(filtered, col.key);
      out.push({ kind: 'header', key: col.key, label: col.label, count: list.length });
      if (!openCols.has(col.key)) continue;
      for (const task of list) {
        out.push({ kind: 'task', key: task.task_id, task });
      }
    }
    return out;
  }, [filtered, openCols]);

  useEffect(() => {
    if (!focusTaskId) return;
    const task = tasks.find((t) => t.task_id === focusTaskId);
    if (!task) return;
    const col = taskColumnKey(task.status);
    setOpenCols((cur) => (cur.has(col) ? cur : new Set(cur).add(col)));
  }, [focusTaskId, tasks]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="ar-h">
        <span className="ar-ht">任務列表</span>
        <span className="ar-hc">{tasks.length}</span>
      </div>
      <div className="ar-search">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜尋任務／ID"
          className="w-full rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-[11px] text-[var(--console-ink)] placeholder:text-[var(--console-sub)] outline-none focus:border-[color-mix(in_srgb,var(--console-accent)_50%,transparent)]"
        />
      </div>
      {filtered.length === 0 ? (
        <p className="px-3 py-8 text-center text-[11px] text-[var(--console-sub)]">
          {tasks.length === 0 ? '尚無任務紀錄' : '無符合結果'}
        </p>
      ) : (
        <Virtuoso
          className="min-h-0 flex-1"
          data={rows}
          computeItemKey={(_i, row) => row.key}
          itemContent={(_i, row) => {
            if (row.kind === 'header') {
              const open = openCols.has(row.key);
              return (
                <button
                  type="button"
                  onClick={() => {
                    setOpenCols((cur) => {
                      const next = new Set(cur);
                      if (next.has(row.key)) next.delete(row.key);
                      else next.add(row.key);
                      return next;
                    });
                  }}
                  className="ar-rg"
                >
                  <span className="inline-block w-2 font-mono text-[var(--console-faint)]">{open ? '▾' : '▸'}</span>
                  <span>{row.label}</span>
                  <span className="ml-auto font-mono text-[10px] text-[var(--console-sub)]">{row.count}</span>
                </button>
              );
            }
            const { task } = row;
            const active = task.task_id === focusTaskId;
            const dot = TASK_STATUS_DOT[task.status] ?? 'bg-[var(--console-sub)]';
            return (
              <button
                type="button"
                onClick={() => onPick(task.task_id)}
                className={`mx-2 mb-0.5 flex w-[calc(100%-16px)] items-center gap-2 rounded-lg px-2.5 py-1.5 text-left transition-colors ${
                  active
                    ? 'bg-white/[0.06] text-[var(--console-ink)]'
                    : 'text-[var(--console-sub)] hover:bg-white/[0.03] hover:text-[var(--console-ink)]'
                }`}
              >
                <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12px] font-medium text-[var(--console-ink)]">
                    {task.query || task.task_id.slice(0, 8)}
                  </span>
                  <span className="block truncate text-[10px] text-[var(--console-sub)]">
                    {task.resolved_path || task.strategy} · {task.phase}
                  </span>
                </span>
              </button>
            );
          }}
        />
      )}
    </div>
  );
}
