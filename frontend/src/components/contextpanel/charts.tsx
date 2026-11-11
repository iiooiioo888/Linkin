/**
 * Context 面板圖表：步驟趨勢柱狀圖與 Token／Timing 環。
 */
import type { ContextInsight } from '../../api/contextInsight';
import { COMPOSITION_META, fmtTokens } from '../../lib/contextUi';
import type { TrendGranularity, TrendMode, TrendRow } from '../../lib/contextUi';
import { KEYS } from './utils';

export function TrendChart({
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
    return <p className="text-[11px] text-[var(--console-sub)]">尚無 LLM 步驟趨勢。</p>;
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

export function TokenTimingRings({ stats }: { stats: ContextInsight['stats'] }) {
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
