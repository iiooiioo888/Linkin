/**
 * 01 概覽 — 任務身分、路由、階段與耗時。
 */
import type { TaskProgress } from '../../types';
import { OPC_PHASES } from '../../types';
import { COMPANY_PHASES, STANDARD_PHASES, phaseIndex } from '../TaskPanel';
import type { EtaInfo } from '../../lib/taskTiming';
import { eventClock, formatDuration, lastEventTsOf } from '../../lib/taskTiming';
import { COMPANY_TEMPLATE_LABEL, PATH_META, STATUS_META, STRATEGY_LABEL } from './labels';
import { Card, Chip, EmptyState, Field, FieldGrid, SectionHead } from './parts';
import { allKanbanItems, num, textField, timeText } from './narrow';

const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'interrupted']);

export default function OverviewSection({ task, eta }: { task: TaskProgress; eta: EtaInfo | null }) {
  const isCompany = task.resolved_path === 'company';
  const isOPC = task.resolved_path === 'opc';
  const phases: { key: string; label: string }[] = isOPC
    ? OPC_PHASES
    : isCompany
      ? COMPANY_PHASES
      : STANDARD_PHASES;
  const running = task.status === 'running' || task.status === 'pending';
  const failed = task.status === 'failed' || task.status === 'cancelled' || task.status === 'interrupted';
  const idx = phaseIndex(phases, task.phase);
  const items = allKanbanItems(task);
  const doneIds = new Set((task.kanban?.done ?? []).map((i) => i.id));
  const done = items.filter((i) => doneIds.has(i.id)).length;
  const path = PATH_META[task.resolved_path] ?? PATH_META[''];
  const status = STATUS_META[task.status] ?? { label: task.status || '未知', tone: 'var(--apple-gray)' };
  const templateLabel = task.template
    ? `${COMPANY_TEMPLATE_LABEL[task.template] || task.template}（${task.template}）`
    : '';

  return (
    <>
      <SectionHead
        index={1}
        title="概覽"
        hint="任務身分、執行路由與階段進度"
        right={
          <span className="apple-data" style={{ color: status.tone }}>
            ● {status.label}
          </span>
        }
      />

      <div className="mb-3">
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <span className="text-[9px] font-semibold uppercase tracking-[0.06em] text-[var(--apple-tertiary)]">
            管線階段
          </span>
          <span className="apple-data text-[10px] text-[var(--apple-secondary)]">
            {idx >= 0 ? phases[idx]?.label : task.phase || '尚未進入階段'}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {phases.map((p, i) => {
            const active = running && i === idx;
            const passed = failed ? i < idx : i < idx || (!running && i <= idx);
            return (
              <div key={p.key} className="flex min-w-0 flex-1 flex-col items-center gap-1">
                <div
                  className={`h-1.5 w-full rounded-full transition-colors ${
                    failed && i === idx
                      ? 'bg-[var(--apple-red)]'
                      : passed
                        ? 'bg-[var(--apple-blue)]'
                        : active
                          ? 'progress-shimmer'
                          : 'bg-white/[0.07]'
                  }`}
                />
                <span
                  className={`whitespace-nowrap text-[9.5px] ${
                    active
                      ? 'text-[var(--apple-blue-soft)]'
                      : passed
                        ? 'text-[var(--apple-secondary)]'
                        : 'text-[var(--apple-tertiary)]'
                  }`}
                >
                  {p.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <FieldGrid>
        <Field
          label="原始需求（query）"
          wide
          value={<span className="whitespace-pre-wrap break-words">{task.query || '（空）'}</span>}
        />
        <Field label="執行策略（strategy）" value={STRATEGY_LABEL[task.strategy] ?? task.strategy ?? '—'} />
        <Field
          label="實際路徑（resolved_path）"
          value={
            <span style={{ color: path.tone }}>
              {path.icon} {path.label}
            </span>
          }
        />
        <Field label="組織模板（template）" value={templateLabel} />
        <Field label="當前階段（phase）" value={phases[idx]?.label ?? task.phase ?? '—'} />
        <Field
          label="評分（score）"
          value={
            task.score == null
              ? '—'
              : `${task.score}${task.options?.pass_threshold ? ` ／ 門檻 ${task.options.pass_threshold}` : ''}`
          }
          tone={
            task.score != null && Number(task.score) >= (num(task.options?.pass_threshold) ?? 80)
              ? 'var(--apple-green)'
              : undefined
          }
        />
        <Field label="迭代輪數（iteration）" value={String(task.iteration ?? 0)} />
        <Field
          label="工作項"
          value={items.length ? `${done} ／ ${items.length} 已完成` : '無（直通任務不產生看板）'}
        />
        <Field label="建立時間（created_at）" value={timeText(task.created_at)} />
        <Field label="已耗時間" value={eta ? formatDuration(eta.elapsedSec) : '—'} />
        <Field
          label="預計剩餘（ETA）"
          value={
            !eta
              ? '—'
              : TERMINAL.has(task.status)
                ? `已結束於 ${eventClock(lastEventTsOf(task))}`
                : eta.remainingSec != null
                  ? `≈ ${formatDuration(eta.remainingSec)}（全程 ≈ ${formatDuration(eta.totalSec ?? eta.elapsedSec)}）`
                  : '樣本累積中（跑過第一個階段後給出估算）'
          }
        />
        <Field
          label="任務 ID"
          wide
          value={
            <span className="flex flex-wrap items-center gap-1.5">
              <span className="apple-data">{task.task_id}</span>
              <Chip tone="#bf5af2">RAHO run：{task.raho?.run_id || '尚未建立'}</Chip>
              {task.cancel_requested ? <Chip tone="var(--apple-orange)">已請求取消</Chip> : null}
              {task.resumable ? <Chip tone="var(--apple-green)">有檢查點，可斷點續跑</Chip> : null}
            </span>
          }
        />
      </FieldGrid>

      {task.error ? (
        <Card className="mt-2" tone="var(--apple-red)">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-[var(--apple-red)]">
            錯誤（error）
          </div>
          <p className="whitespace-pre-wrap break-words text-[11.5px] leading-relaxed text-[var(--apple-red)]">
            {textField(task.error)}
          </p>
        </Card>
      ) : null}

      <div className="mt-3">
        <div className="mb-1.5 text-[9px] font-semibold uppercase tracking-[0.06em] text-[var(--apple-tertiary)]">
          執行參數（options）
        </div>
        <FieldGrid>
          <Field label="預算上限（budget_limit）" value={num(task.options?.budget_limit) ?? '未設定（走預設）'} />
          <Field label="最大並行（max_parallel）" value={num(task.options?.max_parallel) ?? '—'} />
          <Field label="最大迭代（max_iterations）" value={num(task.options?.max_iterations) ?? '—'} />
          <Field label="最大審查輪（max_review_rounds）" value={num(task.options?.max_review_rounds) ?? '—'} />
          <Field label="通過門檻（pass_threshold）" value={num(task.options?.pass_threshold) ?? '—'} />
          <Field label="模型層級偏好（model_tier）" value={task.options?.model_tier ?? '—'} />
        </FieldGrid>
      </div>

      {running ? (
        <div className="mt-3">
          <EmptyState
            title="任務進行中 — 本頁每 3 秒自動刷新"
            note="分析產物會隨著階段推進逐步填入下方區塊。"
          />
        </div>
      ) : null}
    </>
  );
}
