/**
 * TaskPanel — 任務介面面板（參考 PysdnOPC 任務列表風格）。
 *
 * 公司模式：角色流水線芯片 + 子項三欄 + 事件時間軸；標準模式：階段進度 + 評分軌跡。
 *
 * 第八輪重構：常數／型別與看板、時間軸、進度條子元件已拆至 ./taskpanel/；
 * 本檔保留全部 state／memos 與主體 JSX（hooks 呼叫順序與資料流不變）。
 */

import { useMemo, useState } from 'react';
import type { KanbanItem } from '../../types';
import { OPC_PHASES, usesIndustrialStages } from '../../types';
import { eventClock, formatDuration, lastEventTsOf, taskEta, useNowTick } from '../../lib/taskTiming';
import RahoDecisionBar from '../RahoDecisionBar';
import { KanbanBoard } from './KanbanBoard';
import { PhaseProgress } from './PhaseProgress';
import { TimelineBlock } from './TimelineBlock';
import { RoleIcon } from './RoleIcon';
import { COMPANY_PHASES, STANDARD_PHASES, phaseIndex } from './phases';
import { roleLabel } from './roleMeta';
import type { RoleStatus, TaskPanelProps } from './types';

export default function TaskPanel({
  task,
  onOpenFull,
  onCancel,
  onResume,
  onOpenTrace,
  onOpenContext,
  hideDecision = false,
}: TaskPanelProps) {
  const [showTimeline, setShowTimeline] = useState(false);
  const [resuming, setResuming] = useState(false);
  const isOPC = usesIndustrialStages(task);
  const isCompany = task.resolved_path === 'company' || task.resolved_path === 'opc';
  const isCancelled = task.status === 'cancelled';
  const isInterrupted = task.status === 'interrupted';
  const compactTerminal = isCancelled || isInterrupted;
  const phases = isOPC ? OPC_PHASES : isCompany ? COMPANY_PHASES : STANDARD_PHASES;
  const running = task.status === 'running' || task.status === 'pending';
  const failed = task.status === 'failed' || isCancelled || isInterrupted;
  const currentIdx = phaseIndex(phases, task.phase);

  // ── 公司模式：按角色分組工作項 ──
  const roleGroups = useMemo(() => {
    if (!isCompany) return [];
    const groups = new Map<string, { status: string; item: KanbanItem }[]>();
    for (const [status, items] of Object.entries(task.kanban)) {
      for (const item of items) {
        const role = item.assignee || 'developer';
        if (!groups.has(role)) groups.set(role, []);
        groups.get(role)!.push({ status, item });
      }
    }
    return [...groups.entries()].map(([role, entries]) => {
      const statusSet = new Set(entries.map((e) => e.status));
      let status: RoleStatus = 'pending';
      if (statusSet.has('executing')) status = 'active';
      else if (statusSet.has('blocked')) status = 'failed';
      else if (statusSet.has('in_review') || statusSet.has('rework') || statusSet.has('ready')) status = 'waiting';
      else if ([...statusSet].every((s) => s === 'done')) status = 'done';
      return { role, status, entries };
    });
  }, [isCompany, task.kanban]);

  // 流水線特殊角色狀態
  const managerStatus: RoleStatus =
    task.phase === 'decompose' || task.phase === 'final_review'
      ? 'active'
      : currentIdx > 0 || task.status === 'completed'
        ? 'done'
        : 'pending';
  const reviewerStatus: RoleStatus =
    (task.kanban.in_review?.length ?? 0) > 0
      ? 'active'
      : (task.kanban.done?.length ?? 0) > 0
        ? 'done'
        : 'pending';
  const synthesizerStatus: RoleStatus =
    task.phase === 'synthesize' ? 'active' : currentIdx > 2 || task.status === 'completed' ? 'done' : 'pending';

  // ── 流水線芯片（特殊角色只出現一次，工作項明細仍保留分組） ──
  const SPECIAL_ROLES = new Set(['manager', 'reviewer', 'synthesizer']);
  const pipeline: { key: string; label: string; status: RoleStatus }[] = isCompany
    ? [
        { key: 'manager', label: 'Manager', status: managerStatus },
        ...roleGroups
          .filter((g) => !SPECIAL_ROLES.has(g.role))
          .map((g) => ({ key: g.role, label: roleLabel(g.role), status: g.status })),
        { key: 'reviewer', label: 'Reviewer', status: reviewerStatus },
        { key: 'synthesizer', label: 'Synthesizer', status: synthesizerStatus },
      ]
    : [];

  const evaluations = task.events.filter((e) => e.event === 'evaluation');
  const doneCount = task.kanban.done?.length ?? 0;
  const totalCount = Object.values(task.kanban).reduce((s, items) => s + items.length, 0);

  // ── 工具調用狀態（Agent 工具閉環可視化）──
  const toolCalls = task.events.filter((e) => e.event === 'tool_call');
  const toolResults = task.events.filter((e) => e.event === 'tool_result');
  // 最近一次工具調用（用於執行中顯示）
  const lastToolCall = toolCalls[toolCalls.length - 1];
  const lastToolResult = toolResults[toolResults.length - 1];
  // 判斷最近調用是否仍在進行中（無對應結果）
  const toolPending = lastToolCall && (!lastToolResult || lastToolResult.ts < lastToolCall.ts);

  // ── 耗時／ETA 估算（執行中每秒刷新）──
  const nowMs = useNowTick(running);
  const eta = useMemo(() => taskEta(task, nowMs), [task, nowMs]);
  const etaTip = eta
    ? eta.method === 'insufficient'
      ? '各階段樣本累積中，跑過第一個階段後即給出剩餘時間估算'
      : `估算依據：${
          eta.method === 'items'
            ? '看板工作項完成率＋階段均值'
            : eta.method === 'loops+phase'
              ? '反思閉環剩餘迭代 × 階段均值'
              : '已完成階段的歷史均值'
        }${
          Object.keys(eta.phaseAvg).length
            ? `（${Object.entries(eta.phaseAvg)
                .map(([k, v]) => `${k} ≈ ${Math.round(v)}s`)
                .join('、')}）`
            : ''
        }`
    : '';

  return (
    <div className="evo-task-card mb-2 w-full min-w-[240px] p-3 text-xs">
      {/* ── 標題列 ── */}
      <div className="flex items-center gap-2">
        {running && (
          <span className="inline-block h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
        )}
        {failed && <span>{isCancelled ? '🚫' : isInterrupted ? '🔌' : '❌'}</span>}
        {task.status === 'completed' && <span>✅</span>}
        <span className="font-medium text-gray-100">
          {isOPC ? '🏭 OPC 診斷' : isCompany ? '🏢 公司任務' : '⚙️ 反思任務'}
        </span>
        <span className="truncate text-[var(--console-faint)]">
          {running
            ? `${phases[currentIdx]?.label ?? task.phase}${totalCount > 0 ? ` · ${doneCount}/${totalCount} 工作項` : ''}`
            : isCancelled
              ? '已取消'
              : isInterrupted
                ? '已中斷（服務重啟）'
                : failed
                  ? '執行失敗'
                  : `評分 ${task.score != null ? Math.round(task.score * 100) / 100 : '-'} · 迭代 ${task.iteration}`}
        </span>
        {/* 取消按鈕：執行中且未請求取消時顯示 */}
        {running && !task.cancel_requested && onCancel && (
          <button
            onClick={() => onCancel(task.task_id)}
            className="ml-auto shrink-0 rounded border border-red-500/40 bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)] px-1.5 py-0.5 text-[10px] console-status-danger transition-colors hover:bg-red-500/20"
          >
            ✕ 取消
          </button>
        )}
        {running && task.cancel_requested && (
          <span className="ml-auto shrink-0 text-[10px] text-yellow-400">取消中...</span>
        )}
        {/* 斷點續跑按鈕：任務失敗/取消且有檢查點時顯示 */}
        {!running && task.resumable && onResume && (
          <button
            onClick={() => {
              setResuming(true);
              onResume(task.task_id);
            }}
            disabled={resuming}
            className="ml-auto shrink-0 rounded border border-[var(--console-blue)]/50 bg-[var(--console-blue)]/10 px-1.5 py-0.5 text-[10px] console-status-blue transition-colors hover:bg-[var(--console-blue)]/20 disabled:opacity-50"
          >
            {resuming ? '恢復中...' : '▶ 斷點續跑'}
          </button>
        )}
      </div>

      {!hideDecision && (
        <RahoDecisionBar
          pending={task.raho?.pending_decisions ?? []}
          runId={task.raho?.run_id}
          poll={running || (task.raho?.pending_decisions?.length ?? 0) > 0}
          variant="embed"
        />
      )}

      {/* ── 階段進度條（執行中帶流光；已取消／中斷僅顯示精簡標題） ── */}
      {!compactTerminal && (
        <PhaseProgress phases={phases} currentIdx={currentIdx} running={running} failed={failed} />
      )}


      {/* ── 耗時／預計剩餘 ── */}
      {!compactTerminal && eta && (
        <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px]" title={etaTip}>
          <span className="text-[var(--console-faint)]">
            已耗 <span className="font-medium text-[var(--console-ink)]">{formatDuration(eta.elapsedSec)}</span>
          </span>
          {running ? (
            eta.remainingSec != null ? (
              <>
                <span className="text-gray-600">|</span>
                <span className="text-[var(--console-faint)]">
                  預計剩餘{' '}
                  <span className="font-medium console-status-blue">≈ {formatDuration(eta.remainingSec)}</span>
                </span>
                {eta.totalSec != null && (
                  <span className="text-[var(--console-faint)]">（全程 ≈ {formatDuration(eta.totalSec)}）</span>
                )}
                {eta.curPhaseSec != null && (
                  <span className="text-[var(--console-faint)]">本階段已 {formatDuration(eta.curPhaseSec)}</span>
                )}
              </>
            ) : (
              <span className="text-[var(--console-faint)]">剩餘時間估算中…</span>
            )
          ) : (
            <span className="text-[var(--console-faint)]">
              {task.status === 'completed' ? '完成於' : '結束於'} {eventClock(lastEventTsOf(task))}
            </span>
          )}
        </div>
      )}

      {/* ── 錯誤訊息 ── */}
      {failed && task.error && (
        <p className="mt-2 rounded-lg border border-red-500/25 bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)] px-2.5 py-1.5 leading-relaxed console-status-danger">⚠️ {task.error}</p>
      )}

      {compactTerminal && eta && (
        <p className="mt-2 text-[11px] text-[var(--console-faint)]">
          已耗 {formatDuration(eta.elapsedSec)}
          {isCancelled ? ' · 任務已取消' : ' · 任務已中斷'}
        </p>
      )}

      {/* ── Agent 工具調用狀態 ── */}
      {!compactTerminal && isCompany && toolCalls.length > 0 && (
        <div className="mt-2 rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-2.5 py-1.5">
          <p className="flex items-center gap-1.5 text-[11px] text-cyan-300">
            {toolPending && (
              <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
            )}
            🔧 {toolPending
              ? `正在調用工具 ${String(lastToolCall.data.tool ?? '')}...`
              : `已調用 ${toolCalls.length} 次工具`}
          </p>
          {!toolPending && lastToolResult && (
            <p className="mt-0.5 truncate text-[10px] text-[var(--console-faint)]">
              {lastToolResult.data.success ? '✓' : '✗'} {String(lastToolResult.data.tool ?? '')}
              {lastToolResult.data.observation ? `：${String(lastToolResult.data.observation).slice(0, 80)}` : ''}
            </p>
          )}
        </div>
      )}

      {/* ══ 公司模式：角色流水線（PysdnOPC 風格） ══ */}
      {!compactTerminal && isCompany && pipeline.length > 1 && (
        <div className="mt-3 flex flex-wrap items-center gap-1">
          {pipeline.map((role, i) => (
            <span key={role.key} className="flex items-center gap-1">
              <span
                className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] transition-colors duration-200 ${
                  role.status === 'active'
                    ? 'border-blue-400/60 bg-blue-500/10 text-blue-200 shadow-[0_0_8px_rgba(59,130,246,0.25)]'
                    : role.status === 'done'
                      ? 'border-green-500/40 bg-green-500/10 text-green-200'
                      : role.status === 'failed'
                        ? 'border-red-500/40 bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)] text-red-200'
                        : role.status === 'waiting'
                          ? 'border-yellow-500/40 bg-yellow-500/10 text-yellow-200'
                          : 'border-[var(--console-line)]/70 bg-[var(--console-dim)]/40 text-[var(--console-faint)]'
                }`}
              >
                {role.label}
                <RoleIcon status={role.status} />
              </span>
              {i < pipeline.length - 1 && <span className="text-gray-600">→</span>}
            </span>
          ))}
        </div>
      )}

      {/* ══ 公司模式：子項三欄（隊列 / 執行中 / 已完成） ══ */}
      {!compactTerminal && isCompany && totalCount > 0 && <KanbanBoard roleGroups={roleGroups} />}


      {/* ── 評分軌跡（多輪迭代時） ── */}
      {evaluations.length > 1 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {evaluations.map((e, i) => (
            <span key={i} className="rounded-full bg-[var(--console-dim)] px-2 py-0.5 text-[11px] text-[var(--console-sub)]">
              第 {Number(e.data.iteration ?? 0) + 1} 次：
              <span className="ml-1 font-medium console-status-blue">{String(e.data.score ?? '?')} 分</span>
            </span>
          ))}
        </div>
      )}

      {/* ══ 事件時間軸（可展開） ══ */}
      {isCompany && task.events.length > 0 && (
        <TimelineBlock task={task} showTimeline={showTimeline} setShowTimeline={setShowTimeline} />
      )}


      {/* ── 預算 ── */}
      {isCompany && Object.keys(task.budget).length > 0 && (
        <p className="mt-2 text-[11px] text-[var(--console-faint)]">
          💰 花費 ${String(task.budget.task_spent ?? 0)} / 上限 ${String(task.budget.task_limit ?? '-')}
          <span className="ml-2">模型：{String(task.budget.active_tier ?? '-')}</span>
        </p>
      )}

      {/* ── 操作按鈕列 ── */}
      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {onOpenContext && (
          <button
            type="button"
            onClick={() => onOpenContext(task.task_id)}
            data-testid="task-open-context"
            title="在對話底部詳細區開啟 Context"
            className="flex-1 rounded-lg border border-[var(--console-blue)]/35 bg-[var(--console-blue)]/10 py-1.5 text-[11px] font-medium console-status-blue transition-all duration-200 hover:border-[var(--console-blue)]/70 hover:bg-[var(--console-blue)]/18 active:scale-[0.98]"
          >
            Context 詳細區
          </button>
        )}
        {onOpenFull && (
          <button
            onClick={onOpenFull}
            className="flex-1 rounded-lg border border-[var(--console-line)]/70 bg-[var(--console-dim)]/40 py-1.5 text-[11px] font-medium text-[var(--console-sub)] transition-all duration-200 hover:border-blue-500/70 hover:bg-blue-500/10 hover:console-status-blue active:scale-[0.98]"
          >
            ⛶ 開啟任務頁面
          </button>
        )}
        {onOpenTrace && (
          <button
            onClick={() => onOpenTrace(task.task_id)}
            className="flex-1 rounded-lg border border-[var(--console-line)]/70 bg-[var(--console-dim)]/40 py-1.5 text-[11px] font-medium text-[var(--console-sub)] transition-all duration-200 hover:border-[var(--console-blue)]/70 hover:bg-[var(--console-blue)]/10 hover:console-status-blue active:scale-[0.98]"
          >
            📜 思考過程
          </button>
        )}
      </div>
    </div>
  );
}
