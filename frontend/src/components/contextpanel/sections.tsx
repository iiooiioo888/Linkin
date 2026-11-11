/**
 * Context 面板區塊：KPI 卡、步驟趨勢卡與事件卡。
 */
import type { ContextEventKind, ContextInsight } from '../../api/contextInsight';
import { COMPOSITION_META, EVENT_KIND_META, fmtTokens } from '../../lib/contextUi';
import type { TrendGranularity, TrendMode, TrendRow } from '../../lib/contextUi';
import { TrendChart } from './charts';
import { btnCls, cardCls, KIND_FILTERS } from './utils';

export function KpiGrid({ stats, embed }: { stats: ContextInsight['stats']; embed: boolean }) {
  return (
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
            <p className="text-[10px] text-[var(--console-sub)]">{kpi.label}</p>
            <p className={`mt-1 font-semibold text-[var(--console-ink)] ${embed ? 'text-[15px]' : 'text-[18px]'}`}>
              {kpi.value}
            </p>
          </div>
        ))}
      </div>
  );
}

export function TrendCard({
  trend,
  step,
  onSelectStep,
  mode,
  onSelectMode,
  granularity,
  onSelectGranularity,
  brief,
  selectedTrend,
}: {
  trend: TrendRow[];
  step: number | null;
  onSelectStep: (browserStep: number) => void;
  mode: TrendMode;
  onSelectMode: (mode: TrendMode) => void;
  granularity: TrendGranularity;
  onSelectGranularity: (g: TrendGranularity) => void;
  brief?: ContextInsight['browser']['brief'];
  selectedTrend?: ContextInsight['trend'][number];
}) {
  return (
        <section className={cardCls}>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-[13px] font-semibold text-[var(--console-ink)]">Context Trend · 步驟趨勢</h3>
            <div className="flex flex-wrap gap-1">
              {(['step', 'turn'] as TrendGranularity[]).map((g) => (
                <button
                  key={g}
                  type="button"
                  className={`${btnCls}${granularity === g ? ' !text-[var(--console-accent)]' : ''}`}
                  onClick={() => {
                    onSelectGranularity(g);
                  }}
                >
                  {g === 'step' ? 'Step' : 'Turn'}
                </button>
              ))}
              {(['total', 'delta'] as TrendMode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  className={`${btnCls}${mode === m ? ' !text-[var(--console-accent)]' : ''}`}
                  onClick={() => {
                    onSelectMode(m);
                  }}
                >
                  {m === 'total' ? 'Total' : 'Delta'}
                </button>
              ))}
            </div>
          </div>
          <TrendChart
            trend={trend}
            selected={step}
            mode={mode}
            granularity={granularity}
            onSelect={(s) => {
              onSelectStep(s);
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
            <p className="mt-2 text-[10px] text-[var(--console-sub)]">
              標記：I=Inject · C=Compact · P=Prune · S=Switch。點柱切換 Browser。
              {granularity === 'turn' ? ' Turn＝同 phase 連續步驟合併。' : ''}
            </p>
          )}
        </section>
  );
}

export function EventsCard({
  events,
  kindFilter,
  onSelectKind,
  embed,
}: {
  events: ContextInsight['events'];
  kindFilter: ContextEventKind | 'all';
  onSelectKind: (kind: ContextEventKind | 'all') => void;
  embed: boolean;
}) {
  return (
        <section className={`${cardCls} ${embed ? 'lg:col-span-2' : 'xl:col-span-2'}`}>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-[13px] font-semibold text-[var(--console-ink)]">Context Events</h3>
            <div className="flex flex-wrap gap-1">
              <button
                type="button"
                className={`${btnCls}${kindFilter === 'all' ? ' !text-[var(--console-accent)]' : ''}`}
                onClick={() => onSelectKind('all')}
              >
                全部
              </button>
              {KIND_FILTERS.map((k) => (
                <button
                  key={k}
                  type="button"
                  className={`${btnCls}${kindFilter === k ? ' !text-[var(--console-accent)]' : ''}`}
                  onClick={() => onSelectKind(k)}
                >
                  {EVENT_KIND_META[k].label}
                </button>
              ))}
            </div>
          </div>
          <ul className={`space-y-1.5 overflow-auto ${embed ? 'max-h-48' : 'max-h-80'}`}>
            {events.length === 0 ? (
              <li className="text-[11px] text-[var(--console-sub)]">尚無事件</li>
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
                          <span className="text-[var(--console-ink)]">{ev.producer || ev.event}</span>
                          {ev.phase ? <span className="text-[var(--console-sub)]">{ev.phase}</span> : null}
                        </div>
                        {ev.summary ? (
                          <p className="mt-0.5 truncate text-[10px] text-[var(--console-sub)]">{ev.summary}</p>
                        ) : null}
                      </div>
                      <div className="shrink-0 text-right font-mono text-[10px] text-[var(--console-sub)]">
                        <div>
                          {(ev.delta_tokens || 0) > 0 ? '+' : ''}
                          {fmtTokens(ev.delta_tokens)}
                        </div>
                        <div className="text-[var(--console-sub)]">{ev.ts ? String(ev.ts).slice(11, 19) : ''}</div>
                      </div>
                    </li>
                  );
                })
            )}
          </ul>
        </section>
  );
}
