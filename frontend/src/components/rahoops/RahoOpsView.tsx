/**
 * RahoOpsView — 公司運行時席位 I/O 監察整頁。
 *
 * 三欄：左＝席位名冊（按 RAHO lane 分組）、中＝投遞流水、右＝單次投遞全文。
 * 資料源只有兩個端點：fetchSeatFeed（輕量投影）與 fetchSeatDetail（單條全文）；
 * role／kind 過濾在本頁客戶端完成，避免每次切換都重抓 400 列。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchSeatDetail, fetchSeatFeed } from '../../api/client';
import type {
  RahoPendingDecision,
  SeatFeedQuery,
  SeatIOFeed,
  SeatIOFeedRow,
  SeatIOKind,
  SeatIORecord,
} from '../../types';
import { fmtUsd, fmtWhen } from '../../lib/agentUi';
import RahoDecisionBar from '../RahoDecisionBar';
import SeatFeedList from './SeatFeedList';
import SeatIODrawer from './SeatIODrawer';
import SeatRoster from './SeatRoster';
import { aggregateSeats, feedTotals, normalizeRows } from './seatModel';

type SeatFeedRuns = SeatIOFeed['runs'];

/** 一次抓足名冊聚合用的窗口（後端 limit 上限即環形緩衝容量） */
const FEED_LIMIT = 400;
/** 執行中的輪詢間隔 */
const POLL_MS = 2500;
/** 最近一筆投遞在此窗口內才視為「執行中」，避免對已收尾的 run 無限輪詢 */
const LIVE_WINDOW_MS = 10 * 60 * 1000;

interface RahoOpsViewProps {
  focus: string | null;
  onFocusChange: (focus: string | null) => void;
  onOpenTask: (taskId: string) => void;
  onBack: () => void;
  /** L5 待決斷（選填）：未傳入時由 RahoDecisionBar 自行輪詢 /raho/tree */
  pending?: RahoPendingDecision[];
}

function isRecent(iso: string | undefined, nowMs: number): boolean {
  if (!iso) return false;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return false;
  return nowMs - t <= LIVE_WINDOW_MS;
}

export default function RahoOpsView({
  focus,
  onFocusChange,
  onOpenTask,
  onBack,
  pending,
}: RahoOpsViewProps) {
  const [feed, setFeed] = useState<SeatIOFeedRow[]>([]);
  const [feedMeta, setFeedMeta] = useState<{ source: string; total_roles: number; runs: SeatFeedRuns }>(
    { source: 'memory', total_roles: 0, runs: [] },
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [focusAsTask, setFocusAsTask] = useState(false);
  const [nonce, setNonce] = useState(0);
  const [roleFilter, setRoleFilter] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState<SeatIOKind | null>(null);
  const [selectedIoId, setSelectedIoId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SeatIORecord | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [focusDraft, setFocusDraft] = useState('');

  // ── 餵給：focus 先當 run_id，查無 items 再當 task_id 複查 ──
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const base: SeatFeedQuery = { limit: FEED_LIMIT };
    (async () => {
      try {
        let next = focus ? await fetchSeatFeed({ ...base, run_id: focus }) : await fetchSeatFeed(base);
        let asTask = false;
        if (focus && next.items.length === 0) {
          const byTask = await fetchSeatFeed({ ...base, task_id: focus });
          if (byTask.items.length > 0) {
            next = byTask;
            asTask = true;
          }
        }
        if (cancelled) return;
        setFeed(normalizeRows(next.items));
        setFeedMeta({ source: next.source, total_roles: next.total_roles, runs: next.runs });
        setFocusAsTask(asTask);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError((err as Error).message || '讀取席位投遞失敗');
        setFeed([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [focus, nonce]);

  // 切換聚焦對象時丟掉舊過濾與舊詳情
  useEffect(() => {
    setRoleFilter(null);
    setKindFilter(null);
    setSelectedIoId(null);
    setDetail(null);
    setDetailError(null);
    setFocusDraft(focus ?? '');
  }, [focus]);

  // ── 詳情全文：io_id 變更即重抓，舊請求不得覆蓋新資料 ──
  useEffect(() => {
    if (!selectedIoId) {
      setDetail(null);
      setDetailError(null);
      setDetailLoading(false);
      return;
    }
    let cancelled = false;
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    fetchSeatDetail(selectedIoId)
      .then((rec) => {
        if (cancelled) return;
        setDetail(rec);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setDetailError(err.message || '讀取投遞全文失敗');
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedIoId]);

  const disk = feedMeta.source === 'disk';
  const live = useMemo(() => {
    if (disk) return false;
    if (feed.length === 0) return true; // 新任務還沒投遞，繼續等第一筆
    return isRecent(feed[0]?.ts, Date.now());
  }, [disk, feed]);

  useEffect(() => {
    if (!live) return;
    const t = setInterval(() => setNonce((n) => n + 1), POLL_MS);
    return () => clearInterval(t);
  }, [live]);

  const aggs = useMemo(() => aggregateSeats(feed), [feed]);
  const totals = useMemo(() => feedTotals(feed, feedMeta.total_roles), [feed, feedMeta.total_roles]);

  const byRole = useMemo(
    () => (roleFilter ? feed.filter((r) => r.role === roleFilter) : feed),
    [feed, roleFilter],
  );
  const rows = useMemo(
    () => (kindFilter ? byRole.filter((r) => r.kind === kindFilter) : byRole),
    [byRole, kindFilter],
  );
  const kindCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of byRole) counts[r.kind] = (counts[r.kind] || 0) + 1;
    return counts;
  }, [byRole]);
  const selectedRow = useMemo(
    () => (selectedIoId ? feed.find((r) => r.io_id === selectedIoId) ?? null : null),
    [feed, selectedIoId],
  );

  const pickRole = useCallback(
    (role: string) => setRoleFilter((prev) => (prev === role ? null : role)),
    [],
  );
  const resolvedFocus = focusAsTask ? 'task_id' : 'run_id';

  return (
    <div className="rd-shell apple-canvas h-full min-h-0">
      <header className="rd-header">
        <div className="rd-id min-w-0">
          <button
            type="button"
            onClick={onBack}
            className="shrink-0 rounded-[8px] border border-[var(--apple-hairline)] px-2 py-1 text-[11px] text-[var(--apple-secondary)] hover:bg-[var(--apple-surface)] hover:text-[var(--apple-label)]"
          >
            ← 返回
          </button>
          <div className="min-w-0">
            <h2 className="rd-name truncate">席位 I/O 監察</h2>
            <p className="truncate text-[10px] text-[var(--apple-secondary)]">
              公司運行時每一次投遞給模型的 prompt 與回傳全文
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <label className="flex items-center gap-1.5">
            <span className="text-[10px] text-[var(--apple-tertiary)]">聚焦</span>
            <select
              value={focus ?? ''}
              onChange={(ev) => onFocusChange(ev.target.value || null)}
              className="max-w-[15rem] rounded-[8px] border border-[var(--apple-hairline)] bg-[var(--apple-surface)] px-1.5 py-1 font-mono text-[10.5px] text-[var(--apple-label)]"
            >
              <option value="">全部（最近投遞）</option>
              {feedMeta.runs.map((run) => (
                <option key={run.run_id || run.task_id} value={run.run_id || run.task_id}>
                  {(run.run_id || run.task_id).slice(0, 18)} · {run.invocations} 投遞 · {run.role_count} 席位
                </option>
              ))}
            </select>
          </label>
          <input
            value={focusDraft}
            onChange={(ev) => setFocusDraft(ev.target.value)}
            onKeyDown={(ev) => {
              if (ev.key === 'Enter') onFocusChange(focusDraft.trim() || null);
            }}
            placeholder="貼上 run_id / task_id"
            className="w-[9.5rem] rounded-[8px] border border-[var(--apple-hairline)] bg-[var(--apple-surface)] px-1.5 py-1 font-mono text-[10.5px] text-[var(--apple-label)] placeholder:text-[var(--apple-tertiary)]"
          />
          <button
            type="button"
            onClick={() => onFocusChange(focusDraft.trim() || null)}
            className="rounded-[8px] border border-[var(--apple-blue)]/50 bg-[var(--apple-blue)]/12 px-2 py-1 text-[10.5px] text-[var(--apple-label)] hover:bg-[var(--apple-blue)]/25"
          >
            套用
          </button>
          <button
            type="button"
            onClick={() => setNonce((n) => n + 1)}
            title="立即重新整理"
            className="rounded-[8px] border border-[var(--apple-hairline)] px-2 py-1 text-[10.5px] text-[var(--apple-secondary)] hover:bg-[var(--apple-surface)] hover:text-[var(--apple-label)]"
          >
            ⟳
          </button>
        </div>
      </header>

      {focus && (
        <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-[var(--apple-hairline)] px-3 py-1.5 text-[10px] text-[var(--apple-secondary)]">
          <span>
            聚焦 <span className="font-mono text-[var(--apple-label)]">{focus}</span>（以{resolvedFocus === 'task_id' ? ' task_id' : ' run_id'}解析）
          </span>
          {disk && <span style={{ color: 'var(--apple-orange)' }}>資料來源為持久檔（跨重啟歷史，不會輪詢）</span>}
        </div>
      )}

      <div className="empty:hidden px-3 pt-2">
        <RahoDecisionBar pending={pending} runId={focus ?? undefined} poll onResolved={() => setNonce((n) => n + 1)} />
      </div>

      <div className="rd-stats">
        <div className="rd-stat">
          <span className="rd-stat-l">投遞總數</span>
          <span className="rd-stat-v">{totals.count}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">涉及席位</span>
          <span className="rd-stat-v">{totals.roles}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">工作項</span>
          <span className="rd-stat-v">{totals.items}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">總花費</span>
          <span className="rd-stat-v">{fmtUsd(totals.cost)}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">降級／錯誤</span>
          <span className={`rd-stat-v ${totals.degraded + totals.errors > 0 ? 'wn' : 'ok'}`}>
            {totals.degraded}／{totals.errors}
          </span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">資料源</span>
          <span className={`rd-stat-v ${disk ? 'wn' : 'ok'}`}>{disk ? '磁碟' : '記憶體'}</span>
        </div>
        <div className="rd-stat">
          <span className="rd-stat-l">更新</span>
          <span className={`rd-stat-v ${live ? 'ok' : ''}`}>
            {live ? `${(POLL_MS / 1000).toFixed(1)}s 輪詢` : '靜態'}
          </span>
        </div>
      </div>

      {error && (
        <p
          className="shrink-0 border-b border-[var(--apple-hairline)] px-3 py-1.5 text-[11px]"
          style={{ background: 'rgba(255,69,58,.08)', color: 'var(--apple-red)' }}
        >
          {error}
        </p>
      )}

      <div className="rd-body">
        <aside className="flex max-h-[34vh] w-full min-w-0 shrink-0 flex-col border-b border-[var(--apple-hairline)] lg:max-h-none lg:w-[248px] lg:border-b-0 lg:border-r">
          <SeatRoster
            aggs={aggs}
            activeRole={roleFilter}
            loading={loading}
            onSelectRole={pickRole}
            onClearRole={() => setRoleFilter(null)}
          />
        </aside>

        <main className="flex min-h-0 w-full min-w-0 flex-1 flex-col">
          <SeatFeedList
            rows={rows}
            kindCounts={kindCounts}
            kindFilter={kindFilter}
            roleFilter={roleFilter}
            selectedIoId={selectedIoId}
            loading={loading}
            error={error}
            source={feedMeta.source}
            polling={live}
            onKindFilter={setKindFilter}
            onClearRole={() => setRoleFilter(null)}
            onPick={(row) => setSelectedIoId(row.io_id)}
          />
        </main>

        {/* 不用 .rd-rp（其 width/overflow 為 unlayered，會蓋掉本页工具類），改以等效樣式 */}
        <aside className="flex max-h-[46vh] w-full min-w-0 shrink-0 flex-col overflow-hidden border-t border-[var(--apple-hairline)] bg-[#141416] lg:max-h-none lg:w-[420px] lg:border-l lg:border-t-0">
          <SeatIODrawer
            row={selectedRow}
            detail={detail}
            loading={detailLoading}
            error={detailError}
            onOpenTask={onOpenTask}
            onClose={() => setSelectedIoId(null)}
          />
        </aside>
      </div>

      <footer className="flex shrink-0 items-center gap-2 border-t border-[var(--apple-hairline)] px-3 py-1 font-mono text-[9.5px] text-[var(--apple-tertiary)]">
        <span>最近投遞 {fmtWhen(feed[0]?.ts)}</span>
        <span>·</span>
        <span>過濾後 {rows.length}／{feed.length} 列（窗口 {FEED_LIMIT}）</span>
        <span className="ml-auto">點擊中欄任一行取全文</span>
      </footer>
    </div>
  );
}
