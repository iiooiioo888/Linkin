/**
 * SeatRoster — 左欄席位名冊。
 * 每席顯示投遞次數、累計花費、最近時間與降級／錯誤警示。
 */
import { fmtUsd, fmtWhen } from '../../lib/agentUi';
import { RAHO_LAYERS } from '../../lib/rahoUi';
import type { SeatAgg } from './seatModel';

function layerShort(layer: number | null): string {
  if (layer == null || layer === 0 || layer === 1) return '';
  return RAHO_LAYERS[layer]?.short ?? '';
}

function SeatRow({
  agg,
  active,
  onSelect,
}: {
  agg: SeatAgg;
  active: boolean;
  onSelect: (role: string) => void;
}) {
  const hasError = agg.errors > 0;
  const alert = hasError || agg.degraded > 0;
  const tone = hasError ? 'var(--apple-red)' : 'var(--apple-orange)';
  return (
    <button
      type="button"
      onClick={() => onSelect(agg.role)}
      title={`${agg.role} · 投遞 ${agg.count} 次${agg.degraded ? ` · 降級 ${agg.degraded}` : ''}${hasError ? ` · 錯誤 ${agg.errors}` : ''}`}
      className={`block w-full rounded-[8px] border px-2 py-1.5 text-left transition-colors ${
        active
          ? 'border-[var(--apple-blue)]/60 bg-[var(--apple-blue)]/12'
          : 'border-transparent hover:border-[var(--apple-hairline)] hover:bg-[var(--apple-surface)]'
      }`}
    >
      <div className="flex min-w-0 items-center gap-1.5">
        {layerShort(agg.layer) ? (
          <span className="shrink-0 font-mono text-[9.5px] text-[var(--apple-tertiary)]">
            {layerShort(agg.layer)}
          </span>
        ) : null}
        <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium text-[var(--apple-label)]">
          {agg.role_label}
        </span>
        {alert && (
          <span className="h-[6px] w-[6px] shrink-0 rounded-full" style={{ background: tone }} />
        )}
      </div>
      <div className="mt-[3px] flex items-center gap-1.5 font-mono text-[10px] text-[var(--apple-secondary)]">
        <span className="text-[var(--apple-label)]">{agg.count}</span>
        <span className="text-[var(--apple-tertiary)]">投遞</span>
        <span className="text-[var(--apple-tertiary)]">·</span>
        <span>{fmtUsd(agg.cost)}</span>
        <span className="ml-auto truncate text-[9.5px] text-[var(--apple-tertiary)]">
          {fmtWhen(agg.last_ts)}
        </span>
      </div>
      {(hasError || agg.degraded > 0) && (
        <div className="mt-[2px] font-mono text-[9.5px]" style={{ color: tone }}>
          {hasError ? `錯誤 ${agg.errors} 次` : ''}
          {hasError && agg.degraded > 0 ? ' · ' : ''}
          {agg.degraded > 0 ? `降級 ${agg.degraded} 次` : ''}
        </div>
      )}
    </button>
  );
}

export default function SeatRoster({
  aggs,
  activeRole,
  loading,
  onSelectRole,
  onClearRole,
}: {
  aggs: SeatAgg[];
  activeRole: string | null;
  loading: boolean;
  onSelectRole: (role: string) => void;
  onClearRole: () => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--apple-hairline)] px-2.5 py-2">
        <span className="text-[10px] font-medium uppercase tracking-wide text-[var(--apple-tertiary)]">
          席位名冊
          <span className="ml-1 font-mono normal-case text-[var(--apple-secondary)]">{aggs.length}</span>
        </span>
        <button
          type="button"
          onClick={onClearRole}
          disabled={!activeRole}
          className={`rounded-[6px] border px-1.5 py-[3px] text-[10px] transition-colors ${
            activeRole
              ? 'border-[var(--apple-blue)]/50 bg-[var(--apple-blue)]/12 text-[var(--apple-label)] hover:bg-[var(--apple-blue)]/25'
              : 'border-[var(--apple-hairline)] text-[var(--apple-tertiary)]'
          }`}
        >
          全部席位
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 py-1.5">
        {aggs.length === 0 ? (
          loading ? (
            <p className="px-2 py-3 text-[11px] text-[var(--apple-secondary)]">載入座席中…</p>
          ) : (
            <div className="px-2 py-4">
              <p className="text-[11.5px] text-[var(--apple-label)]">尚無投遞紀錄</p>
              <p className="mt-1 text-[10.5px] leading-relaxed text-[var(--apple-secondary)]">
                此聚焦對象在環形緩衝與持久檔都查不到席位投遞。任務開始運轉後回來查看，或以頂部下拉切換其他 run。
              </p>
            </div>
          )
        ) : (
          <>
            <div className="flex flex-col gap-[3px]">
              {aggs.map((agg) => (
                <SeatRow
                  key={agg.role}
                  agg={agg}
                  active={activeRole === agg.role}
                  onSelect={onSelectRole}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
