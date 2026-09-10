/**
 * TaskDetailView — 任務詳情整頁（#/task/{taskId}）。
 *
 * 匯合三個分析產物區塊（01 概覽／02 需求分析／03 作戰計劃）＋
 * 04 看板工作項 ＋ 05 事件時間軸 ＋ 06 預算，全部讀自任務快照
 * （GET /tasks/{id}?events_limit=0 的完整事件流），無額外端點。
 * 執行中每 3 秒回調 onRefresh 讓父層重抓快照。
 *
 * 元件樣式一律走 taskdetail/parts.tsx 的共用小件與 --apple-* token。
 */
import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import type { KanbanItem, TaskProgress } from '../../types';
import { eventClock, taskEta, useNowTick } from '../../lib/taskTiming';
import { fmtUsd } from '../../lib/agentUi';
import { EVENT_TONE, STATUS_META } from './labels';
import {
  allKanbanItems,
  KANBAN_STATUS_ORDER,
  num,
  textField,
  timeText,
} from './narrow';
import {
  AnyValue,
  Card,
  Chip,
  EmptyState,
  JsonBlock,
  LABEL_CLS,
  LongText,
  SectionHead,
} from './parts';
import OverviewSection from './OverviewSection';
import PlanSection from './PlanSection';
import RequirementSection from './RequirementSection';

const ContextPanel = lazy(() => import('../ContextPanel'));

const REFRESH_MS = 3000;
/** 看板狀態 → 顯示標籤（對應 backend/company/state.py::WorkItemStatus）。 */
const KANBAN_LABEL: Record<string, { label: string; tone: string }> = {
  planning: { label: '規劃中', tone: 'var(--apple-tertiary)' },
  ready: { label: '待領取', tone: '#64d2ff' },
  executing: { label: '執行中', tone: 'var(--apple-blue)' },
  in_review: { label: '審查中', tone: 'var(--apple-orange)' },
  rework: { label: '退回重修', tone: '#bf5af2' },
  done: { label: '已完成', tone: 'var(--apple-green)' },
  blocked: { label: '阻塞', tone: 'var(--apple-red)' },
  cancelled: { label: '已取消', tone: 'var(--apple-gray)' },
};

interface TaskDetailViewProps {
  task: TaskProgress | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onBack: () => void;
  onOpenTrace: (taskId: string) => void;
  onOpenRaho: (focus: string) => void;
  onCancel: () => void;
  onResume: () => void;
}

const ANCHORS: Array<{ id: string; label: string }> = [
  { id: 'td-overview', label: '01 概覽' },
  { id: 'td-requirement', label: '02 需求分析' },
  { id: 'td-plan', label: '03 作戰計劃' },
  { id: 'td-board', label: '04 工作項' },
  { id: 'td-events', label: '05 事件流' },
  { id: 'td-context', label: '07 Context' },
];

export default function TaskDetailView({
  task,
  loading,
  error,
  onRefresh,
  onBack,
  onOpenTrace,
  onOpenRaho,
  onCancel,
  onResume,
}: TaskDetailViewProps) {
  const [eventsOpen, setEventsOpen] = useState(false);
  const running = !!task && (task.status === 'running' || task.status === 'pending');
  const nowMs = useNowTick(running, 1000);
  const eta = useMemo(() => (task ? taskEta(task, nowMs) : null), [task, nowMs]);

  // 執行中自動刷新（父層的 loadTaskDetail 負責真正抓資料與防呆）
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => onRefresh(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [running, onRefresh]);

  const status = task ? STATUS_META[task.status] ?? { label: task.status || '未知', tone: 'var(--apple-gray)' } : null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* ── 工具列 ── */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-[var(--apple-hairline)] px-3 py-2">
        <button type="button" className="rd-btn !px-2 !py-[3px] !text-[11px]" onClick={onBack}>
          ← 返回
        </button>
        <span className="truncate text-[12px] font-semibold text-[var(--apple-label)]">
          {task ? task.query.slice(0, 48) || task.task_id : '任務詳情'}
        </span>
        {status ? (
          <Chip tone={status.tone}>● {status.label}</Chip>
        ) : null}
        {running && eta?.remainingSec != null ? (
          <span className="apple-data text-[10px] text-[var(--apple-tertiary)]">
            ETA ≈ {Math.round(eta.remainingSec)}s
          </span>
        ) : null}
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          {task && running ? (
            <button type="button" className="rd-btn !px-2 !py-[3px] !text-[10px]" onClick={onCancel}>
              請求取消
            </button>
          ) : null}
          {task && !running && task.resumable ? (
            <button type="button" className="rd-btn !px-2 !py-[3px] !text-[10px]" onClick={onResume}>
              斷點續跑
            </button>
          ) : null}
          {task ? (
            <button
              type="button"
              className="rd-btn !px-2 !py-[3px] !text-[10px]"
              onClick={() => onOpenRaho(task.raho?.run_id || task.task_id)}
            >
              席位 I/O 監察
            </button>
          ) : null}
          {task ? (
            <button
              type="button"
              className="rd-btn !px-2 !py-[3px] !text-[10px]"
              onClick={() => onOpenTrace(task.task_id)}
            >
              執行軌跡
            </button>
          ) : null}
          <button type="button" className="rd-btn !px-2 !py-[3px] !text-[10px]" onClick={onRefresh}>
            刷新
          </button>
        </div>
      </div>

      {/* ── 錨點導覽 ── */}
      {task ? (
        <div className="flex shrink-0 flex-wrap gap-1 border-b border-[var(--apple-hairline)] px-3 py-1.5">
          {ANCHORS.map((a) => (
            <a
              key={a.id}
              href={`#${a.id}`}
              onClick={(e) => {
                e.preventDefault();
                document.getElementById(a.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                if (a.id === 'td-events') setEventsOpen(true);
              }}
              className="apple-data rounded-[4px] px-1.5 py-[2px] text-[10px] text-[var(--apple-tertiary)] hover:bg-[var(--apple-surface)] hover:text-[var(--apple-secondary)]"
            >
              {a.label}
            </a>
          ))}
        </div>
      ) : null}

      {/* ── 正文 ── */}
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {error ? (
          <Card tone="var(--apple-red)">
            <p className="text-[11.5px] leading-relaxed text-[var(--apple-red)]">
              讀取任務詳情失敗：{error}
            </p>
            <button type="button" className="rd-btn mt-2 !px-2 !py-[3px] !text-[10px]" onClick={onRefresh}>
              重試
            </button>
          </Card>
        ) : null}

        {!task && loading && !error ? (
          <EmptyState title="載入任務快照中…" note="完整事件流（events_limit=0）首次載入可能較慢。" />
        ) : null}

        {!task && !loading && !error ? (
          <EmptyState title="沒有可顯示的任務" note="從任務列表或看板點擊任務即可開啟本頁。" />
        ) : null}

        {task ? (
          <div className="mx-auto max-w-[1100px] space-y-6">
            <section id="td-overview" className="scroll-mt-2">
              <OverviewSection task={task} eta={eta} />
            </section>
            <section id="td-requirement" className="scroll-mt-2">
              <RequirementSection task={task} />
            </section>
            <section id="td-plan" className="scroll-mt-2">
              <PlanSection task={task} />
            </section>

            {/* 04 工作項看板 */}
            <section id="td-board" className="scroll-mt-2">
              <BoardSection task={task} />
            </section>

            {/* 05 事件時間軸 */}
            <section id="td-events" className="scroll-mt-2">
              <SectionHead
                index={5}
                title="事件時間軸"
                hint="公司運行時全事件（含鏡像的 review/grill/work_item）"
                right={
                  <span className="apple-data">
                    {task.events?.length ?? 0} 條
                    {task.events_truncated ? '（已截斷，此頁預設取全量）' : ''}
                  </span>
                }
              />
              <EventTimeline events={task.events ?? []} expanded={eventsOpen} onToggle={setEventsOpen} />
            </section>

            {/* 06 預算與統計 */}
            <section id="td-budget" className="scroll-mt-2">
              <SectionHead index={6} title="預算與統計" hint="token／成本消耗與工作項計數" />
              <div className="grid grid-cols-1 gap-1.5 lg:grid-cols-2">
                <Card>
                  <div className={LABEL_CLS}>預算（budget）</div>
                  <div className="mt-1">
                    {task.budget && Object.keys(task.budget).length ? (
                      <AnyValue value={task.budget} />
                    ) : (
                      <span className="text-[11px] text-[var(--apple-tertiary)]">—</span>
                    )}
                  </div>
                </Card>
                <Card>
                  <div className={LABEL_CLS}>工作項統計（stats）</div>
                  <div className="mt-1">
                    {task.stats && Object.keys(task.stats).length ? (
                      <AnyValue value={task.stats} />
                    ) : (
                      <span className="text-[11px] text-[var(--apple-tertiary)]">
                        無（非公司模式或尚未產生）
                      </span>
                    )}
                  </div>
                  {task.review ? (
                    <JsonBlock value={task.review} label="最終審查結果（review）" />
                  ) : null}
                </Card>
              </div>
            </section>

            {/* 07 Context 洞察（dsh-context 風格） */}
            <section id="td-context" className="scroll-mt-2">
              <SectionHead
                index={7}
                title="Context 洞察"
                hint="組成／趨勢／瀏覽器／注入與剪枝事件（對齊 dsh-context）"
              />
              <Card>
                <div className="td-context-embed max-h-[640px] overflow-auto">
                  <Suspense
                    fallback={
                      <p className="px-2 py-4 text-[11px] text-[var(--apple-tertiary)]">載入 Context…</p>
                    }
                  >
                    <ContextPanel key={`td-ctx-${task.task_id}`} taskId={task.task_id} embed />
                  </Suspense>
                </div>
              </Card>
            </section>
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ── 04 工作項看板 ──

function BoardSection({ task }: { task: TaskProgress }) {
  const items = allKanbanItems(task);
  const byStatus = useMemo(() => {
    const map = new Map<string, KanbanItem[]>();
    for (const item of items) {
      const statusKey = Object.entries(task.kanban ?? {}).find(([, arr]) =>
        (arr ?? []).some((i) => i.id === item.id),
      )?.[0];
      const key = statusKey ?? 'planning';
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(item);
    }
    return map;
  }, [items, task.kanban]);

  return (
    <>
      <SectionHead
        index={4}
        title="工作項"
        hint="Manager 分解出的可執行單元與各自狀態"
        right={<span className="apple-data">{items.length} 項</span>}
      />
      {!items.length ? (
        <EmptyState
          title="無工作項"
          note="直通（simple）／反思迴路任務不產生看板；公司模式在拆解完成後会出现。"
        />
      ) : (
        <div className="grid grid-cols-1 gap-1.5 md:grid-cols-2 xl:grid-cols-3">
          {KANBAN_STATUS_ORDER.filter((s) => byStatus.has(s)).flatMap((statusKey) =>
            (byStatus.get(statusKey) ?? []).map((item) => (
              <KanbanCard key={item.id} item={item} statusKey={statusKey} />
            )),
          )}
        </div>
      )}
    </>
  );
}

function KanbanCard({ item, statusKey }: { item: KanbanItem; statusKey: string }) {
  const meta = KANBAN_LABEL[statusKey] ?? { label: statusKey, tone: 'var(--apple-tertiary)' };
  const lastFeedback = item.feedback?.length ? item.feedback[item.feedback.length - 1] : null;
  return (
    <Card tone={meta.tone}>
      <div className="mb-1 flex items-start justify-between gap-2">
        <span className="min-w-0 break-words text-[11.5px] font-semibold text-[var(--apple-label)]">
          {item.title || item.id}
        </span>
        <Chip tone={meta.tone}>{meta.label}</Chip>
      </div>
      <div className="flex flex-wrap items-center gap-1 text-[10px] text-[var(--apple-tertiary)]">
        <span className="apple-data">{item.id}</span>
        {item.assignee ? <span>· {item.assignee}</span> : null}
        {item.tier ? <span>· {item.tier}</span> : null}
        {item.actual_cost != null ? <span>· {fmtUsd(num(item.actual_cost) ?? 0)}</span> : null}
        {item.depends_on?.length ? <span>· 依賴 {item.depends_on.length}</span> : null}
      </div>
      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0 text-[9.5px] text-[var(--apple-tertiary)]">
        <span>建 {timeText(item.created_at)}</span>
        <span>更 {timeText(item.updated_at)}</span>
        {item.completed_at ? <span className="text-[var(--apple-green)]">完 {timeText(item.completed_at)}</span> : null}
      </div>
      {item.description ? (
        <p className="mt-1 line-clamp-3 text-[10.5px] leading-relaxed text-[var(--apple-secondary)]">
          {item.description}
        </p>
      ) : null}
      {lastFeedback ? (
        <LongText text={textField(lastFeedback)} label={`審查回饋（${item.feedback?.length ?? 0} 輪）`} />
      ) : null}
      {item.output ? <LongText text={textField(item.output)} label="產出物" /> : null}
      {item.thinking ? <LongText text={textField(item.thinking)} label="角色思考" /> : null}
    </Card>
  );
}

// ── 05 事件時間軸 ──

function EventTimeline({
  events,
  expanded,
  onToggle,
}: {
  events: TaskProgress['events'];
  expanded: boolean;
  onToggle: (next: boolean) => void;
}) {
  if (!events.length) {
    return <EmptyState title="尚無事件" note="任務開始執行後事件會即時出現在這裡。" />;
  }
  // 時間軸按時間正序；超過 120 條時默認收攏成最近窗口，展開看全部
  const window = events.length > 120 && !expanded ? events.slice(-120) : events;
  const recentFirst = [...window].reverse();
  return (
    <div>
      {events.length > 120 && !expanded ? (
        <div className="mb-1.5 text-[10.5px] text-[var(--apple-tertiary)]">
          僅顯示最近 120 條／共 {events.length} 條
        </div>
      ) : null}
      <ul className="space-y-1">
        {recentFirst.map((ev, i) => {
          const tone = EVENT_TONE[ev.event];
          const data = ev.data ?? {};
          const bits = [
            typeof data.item_id === 'string' ? (data.item_id as string) : '',
            typeof data.role === 'string' ? (data.role as string) : '',
            typeof data.assignee === 'string' ? (data.assignee as string) : '',
            typeof data.phase === 'string' ? (data.phase as string) : '',
            typeof data.title === 'string' ? (data.title as string).slice(0, 40) : '',
            typeof data.model === 'string' ? (data.model as string) : '',
          ].filter(Boolean);
          const detail = typeof data.output === 'string'
            ? (data.output as string)
            : typeof data.reason === 'string'
              ? (data.reason as string)
              : typeof data.answer === 'string'
                ? (data.answer as string)
                : null;
          return (
            <li key={`${ev.ts}-${i}`} className="flex items-start gap-2 rounded-[6px] px-1.5 py-1 hover:bg-[var(--apple-surface)]">
              <span className="apple-data w-[62px] shrink-0 pt-[2px] text-[10px] text-[var(--apple-tertiary)]">
                {eventClock(ev.ts)}
              </span>
              <span
                className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: tone || 'var(--apple-blue)' }}
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <span
                    className="apple-data text-[10.5px] font-semibold"
                    style={{ color: tone || 'var(--apple-label)' }}
                  >
                    {ev.event}
                  </span>
                  {bits.length ? (
                    <span className="truncate text-[10px] text-[var(--apple-tertiary)]">{bits.join(' · ')}</span>
                  ) : null}
                </div>
                {detail ? <LongText text={detail} label="內容" /> : null}
              </div>
            </li>
          );
        })}
      </ul>
      {events.length > 120 && !expanded ? (
        <button type="button" className="rd-btn mt-2 !px-2 !py-[3px] !text-[10px]" onClick={() => onToggle(true)}>
          展開全部 {events.length} 條
        </button>
      ) : null}
    </div>
  );
}
