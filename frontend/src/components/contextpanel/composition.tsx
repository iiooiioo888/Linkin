/**
 * CompositionBar — 當前上下文組成堆疊條與圖例。
 */
import type { ContextInsight } from '../../api/contextInsight';
import { COMPOSITION_META, fmtTokens } from '../../lib/contextUi';
import { KEYS } from './utils';

export function CompositionBar({
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
            <span key={k} className="inline-flex items-center gap-1.5 text-[10px] text-[var(--console-sub)]">
              <i className="inline-block h-2 w-2 rounded-sm" style={{ background: COMPOSITION_META[k].color }} />
              {COMPOSITION_META[k].short} {fmtTokens(slice.tokens)}
              <span className="text-[var(--console-sub)]">({Math.round((slice.share || 0) * 100)}%)</span>
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
        <p className="mt-2 text-[10px] text-[var(--console-sub)]">相對 Step {vsPrevious.prev_step} 的組成差</p>
      ) : null}
    </div>
  );
}
