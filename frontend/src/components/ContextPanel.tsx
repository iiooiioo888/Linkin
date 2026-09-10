/**
 * Context 面板 — 透視上下文組成、演進、壓縮、剪枝（靈感：dsh-context）。
 *
 * 表面：
 * - 主：對話底部詳細區 embed（ChatBottomPanel Context 分頁）／任務詳情 td-context
 *   → **鎖死當前對話任務**，禁止切換其他對話／全域軌跡
 * - 次：控制台 #/monitor/context[/{taskId}] 完整鏡像（可選任務）
 * - Stats／Composition／Trend／Browser／Events／File／Network／Token＆Timing
 * - 不渲染審計分數槽（C-UI-001）
 *
 * @see https://github.com/bowenliang123/dsh-context
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchContextInsight,
  type CompositionKey,
  type ContextAgentNode,
  type ContextEventKind,
  type ContextFileActivity,
  type ContextInsight,
  type FilePurpose,
} from '../api/contextInsight';
import { fetchTraces } from '../api/client';
import {
  aggregateTrendByTurn,
  COMPOSITION_META,
  EVENT_KIND_META,
  FILE_PURPOSE_META,
  fmtPressure,
  fmtTokens,
  jumpToContext,
  loadTrendGranularity,
  loadTrendMode,
  openChatContextDetail,
  openContextModal,
  parseContextTaskId,
  saveTrendGranularity,
  saveTrendMode,
  sourceChipTone,
  type BrowserSort,
  type TrendGranularity,
  type TrendMode,
  type TrendRow,
} from '../lib/contextUi';
import { jumpToIntegrations, jumpToL0Kernel } from '../lib/rahoUi';
import { fetchPlugins, togglePlugin, type PluginCatalogEntry } from '../api/plugins';

/** embed 無任務時的空洞察（不回落全域最新軌跡） */
function emptyInsightForDialog(message: string): ContextInsight {
  return {
    task_id: null,
    empty: true,
    message,
    stats: {},
    composition: {},
    trend: [],
    events: [],
    steps: [],
    selected_step: null,
    browser: { step: null, categories: {} },
    file_activity: [],
    agent_network: [],
  };
}

const KEYS: CompositionKey[] = ['system', 'tools', 'user', 'injected', 'assistant', 'tool_results'];
const KIND_FILTERS: ContextEventKind[] = ['inject', 'compact', 'prune', 'switch', 'mode'];
const FILE_FILTERS: Array<FilePurpose | 'all'> = ['all', 'read', 'written', 'searched', 'images'];

const btnCls =
  'rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2.5 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8] disabled:opacity-40';
const cardCls = 'rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3';

function CompositionBar({
  composition,
  maxWindow,
  vsPrevious,
}: {
  composition: ContextInsight['composition'];
  maxWindow: number;
  vsPrevious?: ContextInsight['browser']['vs_previous'];
}) {
  const total = KEYS.reduce((s, k) => s + (composition[k]?.tokens || 0), 0);
  const free = Math.max(0, maxWindow - total);
  const denom = Math.max(total + free, 1);
  return (
    <div>
      <div className="ctx-stack" role="img" aria-label="當前上下文組成">
        {KEYS.map((k) => {
          const tok = composition[k]?.tokens || 0;
          if (!tok) return null;
          return (
            <span
              key={k}
              className="ctx-stack-seg"
              style={{
                width: `${(tok / denom) * 100}%`,
                background: COMPOSITION_META[k].color,
              }}
              title={`${COMPOSITION_META[k].label} · ${fmtTokens(tok)}`}
            />
          );
        })}
        {free > 0 ? (
          <span
            className="ctx-stack-seg ctx-stack-free"
            style={{ width: `${(free / denom) * 100}%` }}
            title={`剩餘空間 · ${fmtTokens(free)}`}
          />
        ) : null}
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {KEYS.map((k) => {
          const slice = composition[k];
          if (!slice?.tokens) return null;
          const delta = vsPrevious?.deltas?.[k]?.tokens ?? 0;
          return (
            <span key={k} className="inline-flex items-center gap-1.5 text-[10px] text-[#AEAEB2]">
              <i className="inline-block h-2 w-2 rounded-sm" style={{ background: COMPOSITION_META[k].color }} />
              {COMPOSITION_META[k].short} {fmtTokens(slice.tokens)}
              <span className="text-[#636366]">({Math.round((slice.share || 0) * 100)}%)</span>
              {delta !== 0 ? (
                <span className={`ctx-delta ${delta > 0 ? 'is-up' : 'is-down'}`}>
                  {delta > 0 ? '+' : ''}
                  {fmtTokens(delta)}
                </span>
              ) : null}
            </span>
          );
        })}
      </div>
      {vsPrevious ? (
        <p className="mt-2 text-[10px] text-[#636366]">相對 Step {vsPrevious.prev_step} 的組成差</p>
      ) : null}
    </div>
  );
}

function TrendChart({
  trend,
  selected,
  onSelect,
  mode,
  granularity,
}: {
  trend: TrendRow[];
  selected: number | null;
  onSelect: (browserStep: number) => void;
  mode: TrendMode;
  granularity: TrendGranularity;
}) {
  if (!trend.length) {
    return <p className="text-[11px] text-[#636366]">尚無 LLM 步驟趨勢。</p>;
  }
  const maxAbs =
    mode === 'delta'
      ? Math.max(1, ...trend.map((t) => Math.abs(t.delta_tokens || 0)))
      : Math.max(1, ...trend.map((t) => t.total_tokens || 0));
  return (
    <div className={`ctx-trend${mode === 'delta' ? ' is-delta' : ''}`}>
      {trend.map((row) => {
        const value = mode === 'delta' ? row.delta_tokens || 0 : row.total_tokens || 0;
        const h = Math.max(8, Math.round((Math.abs(value) / maxAbs) * 96));
        const members = row.member_steps?.length ? row.member_steps : [row.step];
        const browserStep = members[members.length - 1]!;
        const active = selected != null && members.includes(selected);
        const bars = mode === 'delta' ? row.delta_bars || row.bars : row.bars;
        const label = granularity === 'turn' ? `Turn ${row.step}` : `Step ${row.step}`;
        return (
          <button
            key={`${granularity}-${row.step}-${browserStep}`}
            type="button"
            className={`ctx-trend-col${active ? ' is-active' : ''}${value < 0 ? ' is-neg' : ''}`}
            onClick={() => onSelect(browserStep)}
            title={`${label} · ${value >= 0 ? '+' : ''}${fmtTokens(value)}${
              members.length > 1 ? ` · ${members.length} steps` : ''
            }`}
          >
            <div className="ctx-trend-bar" style={{ height: h }}>
              {KEYS.map((k) => {
                const v = Math.abs(bars[k] || 0);
                if (!v) return null;
                return (
                  <span
                    key={k}
                    style={{
                      flex: v,
                      background: COMPOSITION_META[k].color,
                    }}
                  />
                );
              })}
            </div>
            <span className="ctx-trend-idx">{row.step}</span>
            {row.marks?.length ? (
              <span className="ctx-trend-marks">
                {row.marks.slice(0, 2).map((m, i) => (
                  <em key={`${m.kind}-${i}`}>{m.kind[0]?.toUpperCase()}</em>
                ))}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

function FileActivityPane({ rows }: { rows: ContextFileActivity[] }) {
  const [filter, setFilter] = useState<FilePurpose | 'all'>('all');
  const [openPath, setOpenPath] = useState<string | null>(null);
  const filtered = rows.filter((r) => filter === 'all' || r.purposes.includes(filter));
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {FILE_FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            className={`${btnCls}${filter === f ? ' !text-[#64D2FF]' : ''}`}
            onClick={() => setFilter(f)}
          >
            {f === 'all' ? '全部' : FILE_PURPOSE_META[f].label}
          </button>
        ))}
      </div>
      {!filtered.length ? (
        <p className="text-[11px] text-[#636366]">尚無檔案讀寫／搜尋活動。</p>
      ) : (
        <ul className="max-h-72 space-y-1 overflow-auto">
          {filtered.map((row) => (
            <li key={row.path} className="rounded-lg border border-white/[0.04] bg-black/20">
              <button
                type="button"
                className="flex w-full items-start justify-between gap-2 px-2 py-1.5 text-left"
                onClick={() => setOpenPath((v) => (v === row.path ? null : row.path))}
              >
                <div className="min-w-0">
                  <p className="truncate font-mono text-[11px] text-[#F5F5F7]">{row.path}</p>
                  <div className="mt-0.5 flex flex-wrap gap-1.5 text-[10px]">
                    {row.purposes.map((p) => (
                      <span key={p} className={FILE_PURPOSE_META[p as FilePurpose]?.tone || 'text-[#8E8E93]'}>
                        {FILE_PURPOSE_META[p as FilePurpose]?.label || p}
                      </span>
                    ))}
                    <span className="text-[#636366]">{row.ops_count} ops</span>
                  </div>
                </div>
                <div className="shrink-0 text-right font-mono text-[10px] text-[#AEAEB2]">
                  {(row.added || row.removed) ? (
                    <span>
                      +{row.added}/−{row.removed}
                    </span>
                  ) : row.hits ? (
                    <span>{row.hits} hits</span>
                  ) : (
                    <span>—</span>
                  )}
                </div>
              </button>
              {openPath === row.path && row.ops?.length ? (
                <ul className="border-t border-white/[0.04] px-2 py-1.5 text-[10px] text-[#8E8E93]">
                  {row.ops.map((op, i) => (
                    <li key={`${op.seq}-${i}`} className="flex justify-between gap-2 py-0.5">
                      <span>
                        {op.tool} · {op.purpose}
                      </span>
                      <span className="font-mono text-[#636366]">{op.ts ? String(op.ts).slice(11, 19) : ''}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AgentNetworkPane({ nodes }: { nodes: ContextAgentNode[] }) {
  if (!nodes.length) {
    return <p className="text-[11px] text-[#636366]">尚無席位／角色呼叫紀錄。</p>;
  }
  const maxTok = Math.max(1, ...nodes.map((n) => (n.tokens_in || 0) + (n.tokens_out || 0)));
  return (
    <div className="ctx-agent-net">
      {nodes.map((n) => {
        const tok = (n.tokens_in || 0) + (n.tokens_out || 0);
        const occ = Math.round((tok / maxTok) * 100);
        return (
          <div key={n.role} className="ctx-agent-node" title={`${n.role} · ${fmtTokens(tok)}`}>
            <div className="ctx-agent-ring" style={{ ['--p' as string]: occ }} />
            <div className="min-w-0">
              <p className="truncate text-[12px] font-medium text-[#F5F5F7]">{n.role}</p>
              <p className="text-[10px] text-[#8E8E93]">
                {n.llm_calls} 次 · {fmtTokens(tok)} · ${(n.cost || 0).toFixed(4)}
              </p>
              {n.parent ? <p className="text-[10px] text-[#636366]">← {n.parent}</p> : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BrowserPane({
  browser,
  onJumpLive,
  isLive,
}: {
  browser: ContextInsight['browser'];
  onJumpLive?: () => void;
  isLive?: boolean;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [catFilter, setCatFilter] = useState<CompositionKey | 'all'>('all');
  const [sort, setSort] = useState<BrowserSort>('size');
  const [query, setQuery] = useState('');

  const sortItems = (items: NonNullable<ContextInsight['browser']['categories'][CompositionKey]>) => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? items.filter(
          (it) =>
            it.label.toLowerCase().includes(q) ||
            String(it.source || '')
              .toLowerCase()
              .includes(q) ||
            String(it.content || '')
              .toLowerCase()
              .includes(q),
        )
      : items;
    const copy = [...filtered];
    if (sort === 'name') {
      copy.sort((a, b) => a.label.localeCompare(b.label, 'zh-Hant'));
    } else {
      copy.sort((a, b) => (b.tokens || 0) - (a.tokens || 0));
    }
    return copy;
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          className={`${btnCls}${isLive ? ' !text-[#30D158]' : ''}`}
          onClick={() => onJumpLive?.()}
          title="Live＝最新一步（下一請求組成）"
        >
          Live
        </button>
        <button
          type="button"
          className={`${btnCls}${catFilter === 'all' ? ' !text-[#64D2FF]' : ''}`}
          onClick={() => setCatFilter('all')}
        >
          全部
        </button>
        {KEYS.map((k) => (
          <button
            key={k}
            type="button"
            className={`${btnCls}${catFilter === k ? ' !text-[#64D2FF]' : ''}`}
            onClick={() => setCatFilter(k)}
          >
            {COMPOSITION_META[k].short}
          </button>
        ))}
        <span className="mx-1 h-4 w-px bg-white/10" />
        <button
          type="button"
          className={`${btnCls}${sort === 'size' ? ' !text-[#64D2FF]' : ''}`}
          onClick={() => setSort('size')}
        >
          依大小
        </button>
        <button
          type="button"
          className={`${btnCls}${sort === 'name' ? ' !text-[#64D2FF]' : ''}`}
          onClick={() => setSort('name')}
        >
          依名稱
        </button>
      </div>
      <input
        className="w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[11px] text-[#F5F5F7] outline-none focus:border-[#64D2FF]/50"
        placeholder="篩選標籤／來源／內容…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {KEYS.filter((k) => catFilter === 'all' || catFilter === k).map((k) => {
        const items = sortItems(browser.categories?.[k] || []);
        if (!items.length) return null;
        return (
          <div key={k} id={`ctx-browser-${k}`} className="rounded-lg border border-white/[0.06] bg-black/20 p-2">
            <div className="mb-1 flex items-center gap-2 text-[11px] font-medium text-[#F5F5F7]">
              <i className="inline-block h-2 w-2 rounded-sm" style={{ background: COMPOSITION_META[k].color }} />
              {COMPOSITION_META[k].label}
              <span className="text-[#636366]">{items.length}</span>
            </div>
            <ul className="space-y-1">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1 text-left text-[11px] text-[#AEAEB2] hover:bg-white/[0.04]"
                    onClick={() => setOpenId((v) => (v === item.id ? null : item.id))}
                  >
                    <span className="min-w-0 truncate">
                      <span className="text-[#F5F5F7]">{item.label}</span>
                      <span className={`ml-2 ${sourceChipTone(item.source)}`}>{item.source}</span>
                    </span>
                    <span className="shrink-0 font-mono text-[10px]">{fmtTokens(item.tokens)}</span>
                  </button>
                  {openId === item.id ? (
                    <pre className="mt-1 max-h-40 overflow-auto rounded-md border border-white/[0.06] bg-black/40 p-2 text-[10px] leading-relaxed text-[#AEAEB2]">
                      {item.content || '（空）'}
                    </pre>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

function TokenTimingRings({ stats }: { stats: ContextInsight['stats'] }) {
  const windowSize = stats.context_window || 128000;
  const used = stats.est_window_tokens || 0;
  const pressurePct = Math.round((stats.context_pressure || 0) * 100);
  const fillPct = Math.min(100, Math.round((used / windowSize) * 100));
  const timing = stats.timing;
  const llmShare = Math.round((timing?.llm_share || 0) * 100);
  return (
    <div className="ctx-rings">
      <div className="ctx-ring">
        <div className="ctx-ring-meter" style={{ ['--p' as string]: fillPct }} aria-hidden />
        <div className="ctx-ring-meta">
          <p className="label">Token 佔用</p>
          <p className="value">
            {fmtTokens(used)} / {fmtTokens(windowSize)}
          </p>
          <p className="label">壓力 {pressurePct}%</p>
        </div>
      </div>
      <div className="ctx-ring">
        <div
          className="ctx-ring-meter"
          style={{
            ['--p' as string]: Math.min(100, llmShare || Math.round(((stats.avg_llm_ms || 0) / 3000) * 100)),
            background: `conic-gradient(#BF5AF2 calc(var(--p) * 1%), rgba(255,255,255,0.08) 0)`,
          }}
          aria-hidden
        />
        <div className="ctx-ring-meta">
          <p className="label">Timing · LLM 佔比</p>
          <p className="value">{llmShare || Math.round(stats.avg_llm_ms || 0)}{timing ? '%' : ' ms'}</p>
          <p className="label">
            工具 {Math.round(timing?.tool_ms || 0)}ms · 開銷 {Math.round(timing?.overhead_ms || 0)}ms · $
            {(stats.est_cost_usd ?? 0).toFixed(4)}
          </p>
        </div>
      </div>
    </div>
  );
}

export default function ContextPanel({
  taskId: taskIdProp,
  embed = false,
}: {
  /** 對話／任務詳情傳入時鎖死此 ID；embed 下禁止改選其他對話 */
  taskId?: string | null;
  /**
   * true＝對話詳細區／任務詳情：
   * - 僅顯示對應對話軌跡
   * - 無任務選擇器、不載入全域 trace 清單
   * - 無 taskId 時顯示空態（不回落 `/context` 最新軌跡）
   * - 後端若回傳其他 task_id 則拒絕顯示
   */
  embed?: boolean;
}) {
  /** embed：永遠跟 prop；控制台：可本地改選 */
  const locked = embed === true;
  const [taskId, setTaskId] = useState<string | null>(() =>
    locked ? taskIdProp ?? null : taskIdProp ?? parseContextTaskId(),
  );
  const [step, setStep] = useState<number | null>(null);
  const [data, setData] = useState<ContextInsight | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [kindFilter, setKindFilter] = useState<ContextEventKind | 'all'>('all');
  const [trendMode, setTrendMode] = useState<TrendMode>(() => loadTrendMode());
  const [trendGran, setTrendGran] = useState<TrendGranularity>(() => loadTrendGranularity());
  const [showPrefs, setShowPrefs] = useState(false);
  const [traceOptions, setTraceOptions] = useState<Array<{ task_id: string; event_count: number }>>([]);
  const [dshPlugin, setDshPlugin] = useState<PluginCatalogEntry | null>(null);
  const [pluginBusy, setPluginBusy] = useState(false);

  useEffect(() => {
    void fetchPlugins()
      .then((p) => {
        const row = p.catalog.find((c) => c.plugin_id === 'dsh-context') || null;
        setDshPlugin(row);
      })
      .catch(() => setDshPlugin(null));
  }, []);

  useEffect(() => {
    if (locked) {
      setTaskId(taskIdProp ?? null);
      setStep(null);
      return;
    }
    if (taskIdProp === undefined) return;
    setTaskId(taskIdProp || null);
    setStep(null);
  }, [taskIdProp, locked]);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      // 對話詳細區：無本對話任務時不回落全域最新軌跡
      if (locked && !taskId) {
        setData(emptyInsightForDialog('本對話尚無任務軌跡。發送任務後將顯示對應 Context。'));
        return;
      }
      const insight = await fetchContextInsight({ taskId, step });
      // embed：若後端誤回其他 task，拒絕顯示（防跨對話）
      if (locked && taskId && insight.task_id && insight.task_id !== taskId) {
        setData(emptyInsightForDialog('軌跡與當前對話不符，已拒絕顯示其他會話 Context。'));
        return;
      }
      setData(insight);
      // 僅控制台允許跟隨 API 解析出的預設任務；embed 絕不跳轉其他對話
      if (!locked && insight.task_id && insight.task_id !== taskId) setTaskId(insight.task_id);
      if (insight.selected_step != null && step == null) setStep(insight.selected_step);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }, [taskId, step, locked]);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 10000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    if (locked) return;
    const onHash = () => {
      const id = parseContextTaskId();
      if (id) {
        setTaskId(id);
        setStep(null);
      }
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, [locked]);

  useEffect(() => {
    if (locked) {
      setTraceOptions([]);
      return;
    }
    void fetchTraces(30)
      .then((r) => setTraceOptions(r.traces.map((t) => ({ task_id: t.task_id, event_count: t.event_count }))))
      .catch(() => setTraceOptions([]));
  }, [locked]);

  const stats = data?.stats ?? {};
  const windowSize = stats.context_window || 128000;
  const events = useMemo(() => {
    const rows = data?.events ?? [];
    if (kindFilter === 'all') return rows;
    return rows.filter((e) => e.kind === kindFilter);
  }, [data?.events, kindFilter]);

  const brief = data?.browser?.brief;
  const displayTrend = useMemo<TrendRow[]>(() => {
    const raw = data?.trend || [];
    return trendGran === 'turn' ? aggregateTrendByTurn(raw) : raw.map((r) => ({ ...r, member_steps: [r.step] }));
  }, [data?.trend, trendGran]);
  const selectedTrend = data?.trend?.find((t) => t.step === step);

  return (
    <div
      className={`ctx-panel${embed ? ' is-embed' : ''} flex min-h-0 flex-1 flex-col overflow-y-auto ${
        embed ? 'px-3 py-2' : 'px-5 py-4'
      } apple-canvas`}
      data-testid={embed ? 'context-panel-embed' : 'context-panel'}
    >
      <header className={embed ? 'ctx-embed-hero' : 'integ-hero'}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2>{embed ? 'Context' : 'Context · 控制台鏡像'}</h2>
            <p>
              {embed
                ? '本對話專屬 · 組成／趨勢／瀏覽器／Inject·Compact·Prune。直接顯示當前對話軌跡，無任務選擇器、不可切換其他會話。輸入 /context 可重新展開。'
                : (
                  <>
                    控制台完整鏡像（主表面在對話底部詳細區）。靈感來自{' '}
                    <a
                      href="https://github.com/bowenliang123/dsh-context"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[#64D2FF] hover:underline"
                    >
                      dsh-context
                    </a>
                    。對話輸入 <code className="text-[10px] text-[#AEAEB2]">/context</code> 優先開詳細區；
                    <code className="ml-1 text-[10px] text-[#AEAEB2]">/context peek</code> 開浮動預覽。
                  </>
                )}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {!embed ? (
              <>
                <button
                  type="button"
                  className={btnCls}
                  onClick={() => openChatContextDetail(taskId)}
                  title="開啟對話底部詳細區（主表面）"
                >
                  對話詳細區
                </button>
                <button
                  type="button"
                  className={btnCls}
                  onClick={() => openContextModal(taskId)}
                  title="浮動 Peek（不離開本頁）"
                >
                  Peek
                </button>
                <button type="button" className={btnCls} onClick={jumpToL0Kernel}>
                  L0 核心
                </button>
                <button type="button" className={btnCls} onClick={() => jumpToIntegrations()}>
                  外部整合
                </button>
              </>
            ) : (
              <button
                type="button"
                className={btnCls}
                onClick={() => openContextModal(taskId)}
                title="浮動 Peek"
              >
                Peek
              </button>
            )}
            <button type="button" className={btnCls} onClick={() => setShowPrefs((v) => !v)}>
              設定
            </button>
            {dshPlugin ? (
              <button
                type="button"
                className={btnCls}
                disabled={pluginBusy}
                title={
                  dshPlugin.enabled
                    ? 'dsh-context 適配已啟用（可視化常駐）'
                    : '顯式啟用 dsh-context 可視化適配'
                }
                onClick={() => {
                  setPluginBusy(true);
                  void togglePlugin('dsh-context', !dshPlugin.enabled)
                    .then((out) => {
                      const row = out.catalog?.find((c) => c.plugin_id === 'dsh-context');
                      if (row) setDshPlugin(row);
                      else setDshPlugin({ ...dshPlugin, enabled: !dshPlugin.enabled, status: !dshPlugin.enabled ? 'enabled' : 'installed' });
                    })
                    .finally(() => setPluginBusy(false));
                }}
              >
                {dshPlugin.enabled ? 'dsh-context · 已啟用' : '啟用 dsh-context'}
              </button>
            ) : null}
            <button type="button" className={btnCls} disabled={busy} onClick={() => void load()}>
              {busy ? '更新中…' : '重新整理'}
            </button>
          </div>
        </div>
        {showPrefs ? (
          <div className="mt-3 rounded-xl border border-white/[0.08] bg-black/25 p-3">
            <p className="mb-2 text-[11px] font-medium text-[#F5F5F7]">Context 偏好（本機）</p>
            <div className="flex flex-wrap gap-3 text-[11px] text-[#AEAEB2]">
              <label className="flex items-center gap-2">
                趨勢粒度
                <select
                  className="rounded-lg border border-white/[0.08] bg-black/40 px-2 py-1 text-[12px] text-[#F5F5F7]"
                  value={trendGran}
                  onChange={(e) => {
                    const g = e.target.value === 'turn' ? 'turn' : 'step';
                    setTrendGran(g);
                    saveTrendGranularity(g);
                  }}
                >
                  <option value="step">Step（每次 LLM）</option>
                  <option value="turn">Turn（同 phase 合併）</option>
                </select>
              </label>
              <label className="flex items-center gap-2">
                趨勢模式
                <select
                  className="rounded-lg border border-white/[0.08] bg-black/40 px-2 py-1 text-[12px] text-[#F5F5F7]"
                  value={trendMode}
                  onChange={(e) => {
                    const m = e.target.value === 'delta' ? 'delta' : 'total';
                    setTrendMode(m);
                    saveTrendMode(m);
                  }}
                >
                  <option value="total">Total（累計組成）</option>
                  <option value="delta">Delta（逐步增減）</option>
                </select>
              </label>
            </div>
          </div>
        ) : null}
        <div className={`mt-3 flex flex-wrap items-end gap-2${embed ? ' ctx-embed-meta' : ''}`}>
          {locked ? (
            <span
              className="rounded-full border border-[#30D158]/25 bg-[#30D158]/10 px-2.5 py-1 font-mono text-[10px] text-[#30D158]"
              data-testid="context-locked-task"
              title="已鎖定本對話任務，無選擇器、不可切換其他會話"
            >
              {taskId ? `🔒 本對話 · ${taskId.slice(0, 12)}…` : '🔒 本對話 · 尚無任務'}
            </span>
          ) : (
            <label className="block text-[10px] text-[#8E8E93]">
              任務
              <select
                className="mt-1 block min-w-[220px] rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px] text-[#F5F5F7]"
                value={taskId || ''}
                onChange={(e) => {
                  const id = e.target.value || null;
                  setTaskId(id);
                  setStep(null);
                  jumpToContext(id);
                }}
                data-testid="context-task-select"
              >
                <option value="">最新軌跡</option>
                {traceOptions.map((t) => (
                  <option key={t.task_id} value={t.task_id}>
                    {t.task_id.slice(0, 12)}… · {t.event_count} 事件
                  </option>
                ))}
              </select>
            </label>
          )}
          {data?.task_id && !locked ? (
            <span className="rounded-full border border-white/[0.08] px-2.5 py-1 font-mono text-[10px] text-[#AEAEB2]">
              {data.task_id}
            </span>
          ) : null}
          <span className="rounded-full border border-white/[0.08] px-2.5 py-1 text-[10px] text-[#AEAEB2]">
            壓力 {fmtPressure(stats.context_pressure)} · 窗 {fmtTokens(stats.est_window_tokens)} /{' '}
            {fmtTokens(windowSize)}
          </span>
        </div>
      </header>

      {error ? (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>
      ) : null}
      {data?.empty ? (
        <div className={`${cardCls} mb-3 text-[12px] text-[#8E8E93]`}>{data.message || '尚無 Context 資料'}</div>
      ) : null}

      <div
        className={`mb-4 grid gap-3 ${
          embed ? 'grid-cols-2 sm:grid-cols-3' : 'sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6'
        }`}
      >
        {[
          { label: 'LLM 呼叫', value: stats.llm_calls ?? 0 },
          { label: '注入次數', value: stats.context_injections ?? 0 },
          { label: '工具呼叫', value: stats.tool_calls ?? 0 },
          { label: 'Compact / Prune', value: `${stats.compacts ?? 0} / ${stats.prunes ?? 0}` },
          { label: '檔案觸及', value: stats.file_touches ?? 0 },
          { label: '估算成本', value: `$${(stats.est_cost_usd ?? 0).toFixed(4)}` },
        ].map((kpi) => (
          <div key={kpi.label} className={cardCls}>
            <p className="text-[10px] text-[#8E8E93]">{kpi.label}</p>
            <p className={`mt-1 font-semibold text-[#F5F5F7] ${embed ? 'text-[15px]' : 'text-[18px]'}`}>
              {kpi.value}
            </p>
          </div>
        ))}
      </div>

      <div className={`mb-4 grid gap-4 ${embed ? 'lg:grid-cols-2' : 'xl:grid-cols-2'}`}>
        <section className={cardCls}>
          <h3 className="mb-2 text-[13px] font-semibold text-[#F5F5F7]">Token / Timing</h3>
          <TokenTimingRings stats={stats} />
        </section>
        <section className={cardCls}>
          <h3 className="mb-2 text-[13px] font-semibold text-[#F5F5F7]">Current Context · 當前組成</h3>
          <CompositionBar
            composition={data?.composition || {}}
            maxWindow={windowSize}
            vsPrevious={data?.browser?.vs_previous}
          />
        </section>
      </div>

      <div className={`grid gap-4 ${embed ? 'lg:grid-cols-2' : 'xl:grid-cols-2'}`}>
        <section className={cardCls}>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-[13px] font-semibold text-[#F5F5F7]">Context Trend · 步驟趨勢</h3>
            <div className="flex flex-wrap gap-1">
              {(['step', 'turn'] as TrendGranularity[]).map((g) => (
                <button
                  key={g}
                  type="button"
                  className={`${btnCls}${trendGran === g ? ' !text-[#64D2FF]' : ''}`}
                  onClick={() => {
                    setTrendGran(g);
                    saveTrendGranularity(g);
                  }}
                >
                  {g === 'step' ? 'Step' : 'Turn'}
                </button>
              ))}
              {(['total', 'delta'] as TrendMode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  className={`${btnCls}${trendMode === m ? ' !text-[#64D2FF]' : ''}`}
                  onClick={() => {
                    setTrendMode(m);
                    saveTrendMode(m);
                  }}
                >
                  {m === 'total' ? 'Total' : 'Delta'}
                </button>
              ))}
            </div>
          </div>
          <TrendChart
            trend={displayTrend}
            selected={step}
            mode={trendMode}
            granularity={trendGran}
            onSelect={(s) => {
              setStep(s);
            }}
          />
          {brief || selectedTrend ? (
            <div className="ctx-step-brief">
              {(
                [
                  ['User', brief?.user || '—', 'user'],
                  [
                    'In',
                    `${brief?.in || selectedTrend?.phase || '—'}${
                      selectedTrend?.marks?.length
                        ? ` · ${selectedTrend.marks.map((m) => m.kind).join('/')}`
                        : ''
                    }`,
                    'injected',
                  ],
                  ['Response', brief?.response || brief?.model || '—', 'assistant'],
                ] as const
              ).map(([k, text, jumpKey]) => (
                <button
                  key={k}
                  type="button"
                  className="row ctx-brief-jump"
                  title={`在 Browser 展開 ${COMPOSITION_META[jumpKey].label}`}
                  onClick={() => {
                    /* 保持當前 step；瀏覽器內以類別篩選由用戶點類別 chip */
                    const el = document.getElementById(`ctx-browser-${jumpKey}`);
                    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                  }}
                >
                  <span className="k">{k}</span>
                  <span className="truncate text-left">{text}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-[10px] text-[#636366]">
              標記：I=Inject · C=Compact · P=Prune · S=Switch。點柱切換 Browser。
              {trendGran === 'turn' ? ' Turn＝同 phase 連續步驟合併。' : ''}
            </p>
          )}
        </section>

        <section className={cardCls}>
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-[13px] font-semibold text-[#F5F5F7]">Context Browser</h3>
            <span className="text-[10px] text-[#636366]">
              {step == null ? 'Live' : `Step ${step}`}
            </span>
          </div>
          <BrowserPane
            browser={data?.browser || { step: null, categories: {} }}
            isLive={step == null || step === (data?.steps?.length ? data.steps.length - 1 : null)}
            onJumpLive={() => {
              const last = data?.steps?.length ? data.steps.length - 1 : null;
              setStep(last);
            }}
          />
        </section>

        <section className={`${cardCls} ${embed ? 'lg:col-span-2' : 'xl:col-span-2'}`}>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-[13px] font-semibold text-[#F5F5F7]">Context Events</h3>
            <div className="flex flex-wrap gap-1">
              <button
                type="button"
                className={`${btnCls}${kindFilter === 'all' ? ' !text-[#64D2FF]' : ''}`}
                onClick={() => setKindFilter('all')}
              >
                全部
              </button>
              {KIND_FILTERS.map((k) => (
                <button
                  key={k}
                  type="button"
                  className={`${btnCls}${kindFilter === k ? ' !text-[#64D2FF]' : ''}`}
                  onClick={() => setKindFilter(k)}
                >
                  {EVENT_KIND_META[k].label}
                </button>
              ))}
            </div>
          </div>
          <ul className={`space-y-1.5 overflow-auto ${embed ? 'max-h-48' : 'max-h-80'}`}>
            {events.length === 0 ? (
              <li className="text-[11px] text-[#636366]">尚無事件</li>
            ) : (
              events
                .slice()
                .reverse()
                .map((ev, idx) => {
                  const meta = EVENT_KIND_META[(ev.kind as ContextEventKind) || 'mode'] || EVENT_KIND_META.mode;
                  return (
                    <li
                      key={`${ev.seq}-${idx}`}
                      className="flex items-start justify-between gap-2 rounded-lg border border-white/[0.04] bg-black/20 px-2 py-1.5"
                    >
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2 text-[11px]">
                          <span className={meta.tone}>{meta.label}</span>
                          <span className="text-[#F5F5F7]">{ev.producer || ev.event}</span>
                          {ev.phase ? <span className="text-[#636366]">{ev.phase}</span> : null}
                        </div>
                        {ev.summary ? (
                          <p className="mt-0.5 truncate text-[10px] text-[#8E8E93]">{ev.summary}</p>
                        ) : null}
                      </div>
                      <div className="shrink-0 text-right font-mono text-[10px] text-[#AEAEB2]">
                        <div>
                          {(ev.delta_tokens || 0) > 0 ? '+' : ''}
                          {fmtTokens(ev.delta_tokens)}
                        </div>
                        <div className="text-[#636366]">{ev.ts ? String(ev.ts).slice(11, 19) : ''}</div>
                      </div>
                    </li>
                  );
                })
            )}
          </ul>
        </section>

        <section className={cardCls}>
          <h3 className="mb-2 text-[13px] font-semibold text-[#F5F5F7]">File Activity · 檔案活動</h3>
          <FileActivityPane rows={data?.file_activity || []} />
        </section>

        <section className={cardCls}>
          <h3 className="mb-2 text-[13px] font-semibold text-[#F5F5F7]">Agent Network · 席位網</h3>
          <AgentNetworkPane nodes={data?.agent_network || []} />
        </section>
      </div>
    </div>
  );
}
