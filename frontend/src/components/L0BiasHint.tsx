/**
 * L0 環境偏置提示：對話卡、質詢樹、即時產出共用。
 */
import type { L0Snapshot } from '../types';
import { jumpToL0Kernel } from '../lib/rahoUi';

export function L0BiasHint({
  snapshot,
  compact = false,
}: {
  snapshot?: L0Snapshot | null;
  compact?: boolean;
}) {
  const radar = snapshot?.radar;
  if (!radar?.bias_instructions && !snapshot?.knowledge?.[0] && !snapshot?.traces?.[0]) {
    return null;
  }
  const pressure = Math.round((radar?.pressure ?? 0) * 100);
  const knowledge = snapshot?.knowledge?.[0];
  return (
    <button type="button" className={`l0-live${compact ? ' is-compact' : ''}`} onClick={jumpToL0Kernel}>
      <div>
        <p>
          L0 環境偏置{radar?.energy_save ? ' · 節能模式' : ''}
          {pressure ? ` · 壓力 ${pressure}%` : ''}
        </p>
        <span>{radar?.bias_instructions || knowledge?.content || snapshot?.traces?.[0]?.summary}</span>
      </div>
      <span>開核心</span>
    </button>
  );
}
