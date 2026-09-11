/**
 * TasksMonitorPanel — 任務視角監控。
 *
 * 以任務為中心：統計概覽、狀態篩選、列表／看板、即時詳情。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { cancelTask, fetchTask, resumeTask } from '../api/client';
import { TASK_COLUMNS, taskColumnKey, tasksInColumn, type TaskColumnKey } from '../lib/agentUi';
import { useMonitorStore } from '../stores/monitorStore';
import type { TaskProgress, TaskSummary } from '../types';
import { StatusColumnBoard } from './StatusColumnBoard';
import TaskPanel, {
  COMPANY_PHASES,
  OPC_PHASES,
  STANDARD_PHASES,
  phaseIndex,
} from './TaskPanel';
import { buildStatusStack, buildTaskDistributionMatrix, taskPriority } from '../lib/monitorData';
import ErrorState from './ui/ErrorState';
import { StackBar, TaskDistributionMatrix, TaskPriorityCard } from './ui/monitor';
import { WarnBar, consoleLayout } from './ui/ConsoleLayout';

interface TasksMonitorPanelProps {
  focusTaskId: string | null;
  onFocusTask: (id: string | null) => void;
  onOpenTask: (task: TaskProgress) => void;
  onOpenTrace?: (taskId: string) => void;
}

type StatusFilter = TaskColumnKey;

const STATUS_META: Record<string, { label: string; cls: string; dot: string }> = {
  pending: { label: '隊列', cls: 'text-[#FF9500]', dot: 'bg-[#FF9500]' },
  running: { label: '執行中', cls: 'text-[#007AFF]', dot: 'bg-[#007AFF]' },
  completed: { label: '已完成', cls: 'text-[#34C759]', dot: 'bg-[#34C759]' },
  failed: { label: '失敗', cls: 'text-[#FF3B30]', dot: 'bg-[#FF3B30]' },
  cancelled: { label: '已取消', cls: 'text-[#8E8E93]', dot: 'bg-[#8E8E93]' },
  interrupted: { label: '中斷', cls: 'text-[#FF9500]', dot: 'bg-[#FF9500]' },
};

const PATH_META: Record<string, { icon: string; label: string }> = {
  simple: { icon: '⚙', label: '反思' },
  company: { icon: '🏢', label: '公司' },
  opc: { icon: '🏭', label: 'OPC' },
};


function relTime(sec: number): string {
  const diff = Math.floor(Date.now() / 1000 - sec);
  if (diff < 60) return '剛剛';
  const m = Math.floor(diff / 60);
  if (m < 60) return `${m} 分鐘前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小時前`;
  return new Date(sec * 1000).toLocaleDateString('zh-TW');
}

function fmtDur(sec: number): string {
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  return m < 60 ? `${m}m ${sec % 60}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

function phasesFor(task: TaskSummary) {
  if (task.resolved_path === 'opc') return OPC_PHASES;
  if (task.resolved_path === 'company') return COMPANY_PHASES;
  return STANDARD_PHASES;
}


function PhaseStrip({ task }: { task: TaskSummary }) {
  const phases = phasesFor(task);
  const idx = phaseIndex(phases, task.phase);
  const running = task.status === 'running' || task.status === 'pending';
  const failed = task.status === 'failed' || task.status === 'cancelled';

  return (
    <div className="mt-2 flex items-center gap-0.5">
      {phases.map((p, i) => {
        const active = running && i === idx;
        const passed = failed ? i < idx : i < idx || (!running && i <= idx);
        return (
          <div
            key={p.key}
            title={p.label}
            className={`h-1 flex-1 rounded-full transition-colors ${
              failed && i === idx
                ? 'bg-[#FF3B30]'
                : passed
                  ? 'bg-[#007AFF]'
                  : active
                    ? 'progress-shimmer'
                    : 'bg-white/[0.08]'
            }`}
          />
        );
      })}
    </div>
  );
}

function TaskCard({
  task,
  active,
  onClick,
}: {
  task: TaskSummary;
  active: boolean;
  onClick: () => void;
}) {
  const meta = STATUS_META[task.status] ?? STATUS_META.pending;
  const path = PATH_META[task.resolved_path] ?? PATH_META.simple;
  const shortId = task.task_id.replace(/^.*[#-]/, '').slice(-4) || task.task_id.slice(0, 4);
  const priority = taskPriority(task);

  return (
    <TaskPriorityCard
      priority={priority}
      title={task.query || '（無標題）'}
      active={active}
      onClick={onClick}
      meta={
        <>
          <span>{meta.label}</span>
          <span>{path.icon} {path.label}</span>
          <span>#{shortId}</span>
          <span>{relTime(task.created_at)}</span>
          {task.score != null ? <span>{Math.round(task.score * 100) / 100} 分</span> : null}
        </>
      }
    >
      <PhaseStrip task={task} />
    </TaskPriorityCard>
  );
}

export default function TasksMonitorPanel({
  focusTaskId,
  onFocusTask,
  onOpenTask,
  onOpenTrace,
}: TasksMonitorPanelProps) {
  const dashboard = useMonitorStore((s) => s.dashboard);
  const connected = useMonitorStore((s) => s.connected);
  const storeError = useMonitorStore((s) => s.error);

  const [filter, setFilter] = useState<StatusFilter>('running');
  const [detail, setDetail] = useState<TaskProgress | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const tasks = dashboard?.tasks ?? [];
  const stats = dashboard?.stats;

  const runningIds = useMemo(
    () => tasks.filter((t) => t.status === 'running' || t.status === 'pending').map((t) => t.task_id),
    [tasks],
  );

  const loadDetail = useCallback(async (taskId: string) => {
    setDetailLoading(true);
    setDetailError(null);
    try {
      const full = await fetchTask(taskId);
      setDetail(full);
    } catch (err) {
      setDetailError((err as Error).message);
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (focusTaskId) void loadDetail(focusTaskId);
    else setDetail(null);
  }, [focusTaskId, loadDetail]);

  // 執行中任務高頻刷新詳情
  useEffect(() => {
    if (!focusTaskId || !runningIds.includes(focusTaskId)) return;
    const timer = setInterval(() => void loadDetail(focusTaskId), 3000);
    return () => clearInterval(timer);
  }, [focusTaskId, runningIds, loadDetail]);

  const handleCancel = async (taskId: string) => {
    try {
      await cancelTask(taskId);
      if (focusTaskId === taskId) void loadDetail(taskId);
    } catch {
      /* ignore */
    }
  };

  const handleResume = async (taskId: string) => {
    try {
      await resumeTask(taskId);
      void loadDetail(taskId);
    } catch {
      /* ignore */
    }
  };

  const pick = (taskId: string) => {
    onFocusTask(taskId);
    setFilter(taskColumnKey(tasks.find((t) => t.task_id === taskId)?.status ?? 'pending'));
  };
  const queueCount = tasksInColumn(tasks, 'queue').length;
  const runningCount = tasksInColumn(tasks, 'running').length;
  const doneCount = tasksInColumn(tasks, 'done').length;
  const statusStack = buildStatusStack(stats ?? {});
  const taskMatrix = buildTaskDistributionMatrix(tasks);
  const capacityWarn = runningCount >= 10;

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden apple-canvas">
      <div className="rd-th">
        <h2>任務列表 — {tasks.length}</h2>
        <span className="apple-data text-[10px] text-[#636366]">
          {connected ? '即時同步' : '離線資料'}
        </span>
      </div>

      {storeError && (
        <div className="shrink-0 px-6 pt-2">
          <ErrorState kind="partial" message={storeError} compact />
        </div>
      )}

      {capacityWarn ? (
        <div className="shrink-0 px-4 py-2">
          <WarnBar>
            執行中任務達 {runningCount} 項 — 建議檢查容量與佇列
          </WarnBar>
        </div>
      ) : null}

      {statusStack.length > 0 ? (
        <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-2">
          <StackBar segments={statusStack} />
        </div>
      ) : null}

      <div className="rd-stats">
        <div className="rd-stat">
          <span className="rd-stat-l">隊列</span>
          <span className="rd-stat-v">{queueCount}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">執行中</span>
          <span className="rd-stat-v">{runningCount}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">已完成</span>
          <span className={`rd-stat-v ${doneCount ? 'ok' : ''}`}>{stats?.tasks_completed ?? doneCount}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">失敗</span>
          <span className={`rd-stat-v ${(stats?.tasks_failed ?? 0) > 0 ? 'er' : ''}`}>{stats?.tasks_failed ?? 0}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">成功率</span>
          <span className={`rd-stat-v ${(stats?.success_rate ?? 0) > 0 ? 'ok' : ''}`}>{stats?.success_rate ?? 0}%</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">平均評分</span>
          <span className="rd-stat-v">{stats?.avg_score != null ? String(stats.avg_score) : '—'}</span>
        </div>
      </div>

      <div className="rd-body">
        <div className={`rd-tasks ${focusTaskId ? 'lg:max-w-none' : ''}`}>
          {!focusTaskId && tasks.length > 0 ? (
            <div className="mb-3 rounded-lg border border-[var(--console-line)] bg-[var(--console-card)] p-3">
              <TaskDistributionMatrix matrix={taskMatrix} demo={taskMatrix.every((r) => r.every((c) => c.count === 0))} />
            </div>
          ) : null}
          <StatusColumnBoard
            selectedKey={filter}
            onSelect={(key) => setFilter(key as TaskColumnKey)}
            compact={Boolean(focusTaskId)}
            columns={TASK_COLUMNS.map((col) => {
              const colTasks = tasksInColumn(tasks, col.key);
              return {
                key: col.key,
                label: col.label,
                count: colTasks.length,
                children: colTasks.map((task) => (
                  <TaskCard
                    key={task.task_id}
                    task={task}
                    active={focusTaskId === task.task_id}
                    onClick={() => pick(task.task_id)}
                  />
                )),
              };
            })}
          />
        </div>

        {/* 右：詳情 */}
        {focusTaskId && (
          <div className="hidden min-h-0 min-w-0 flex-1 flex-col overflow-y-auto border-l border-white/[0.06] lg:flex">
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-white/[0.06] bg-[#0d0d0f]/95 px-6 py-3 backdrop-blur">
              <p className="truncate text-[12px] font-medium text-[#F5F5F7]">
                {detail?.query ?? focusTaskId.slice(0, 8)}
              </p>
              <button
                type="button"
                onClick={() => onFocusTask(null)}
                className="shrink-0 rounded-lg px-2 py-1 text-[11px] text-[#8E8E93] hover:bg-white/[0.06] hover:text-[#F5F5F7]"
              >
                關閉
              </button>
            </div>
            <div className={consoleLayout.cardBody}>
              {detailLoading && !detail && (
                <p className={`${consoleLayout.emptySm} text-[12px] text-[#636366]`}>載入任務…</p>
              )}
              {detailError && (
                <ErrorState kind="generic" message={detailError} compact />
              )}
              {detail && (
                <>
                  <div className="mb-4 flex flex-wrap gap-3 text-[11px] text-[#8E8E93]">
                    <span>ID {detail.task_id.slice(0, 8)}</span>
                    <span>·</span>
                    <span>{PATH_META[detail.resolved_path]?.label ?? detail.resolved_path}</span>
                    <span>·</span>
                    <span>
                      耗時{' '}
                      {fmtDur(
                        detail.created_at
                          ? Math.max(0, Math.floor(Date.now() / 1000 - detail.created_at))
                          : 0,
                      )}
                    </span>
                  </div>
                  <TaskPanel
                    task={detail}
                    onOpenFull={() => onOpenTask(detail)}
                    onCancel={(id) => void handleCancel(id)}
                    onResume={(id) => void handleResume(id)}
                    onOpenTrace={onOpenTrace}
                  />
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* 行動端詳情（全屏疊層） */}
      {focusTaskId && detail && (
        <div className="fixed inset-0 z-30 flex flex-col bg-[#0d0d0f] lg:hidden">
          <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
            <p className="truncate text-[13px] font-medium">任務詳情</p>
            <button
              type="button"
              onClick={() => onFocusTask(null)}
              className="rounded-lg px-3 py-1 text-[12px] text-[#8E8E93]"
            >
              關閉
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <TaskPanel
              task={detail}
              onOpenFull={() => onOpenTask(detail)}
              onCancel={(id) => void handleCancel(id)}
              onResume={(id) => void handleResume(id)}
              onOpenTrace={onOpenTrace}
            />
          </div>
        </div>
      )}
    </div>
  );
}
