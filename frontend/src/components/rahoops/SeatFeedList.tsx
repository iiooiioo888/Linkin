/**
 * SeatFeedList — 中欄投遞流水：一行一次模型投遞，新→舊。
 * 以 react-virtuoso 虛擬化，避免長清單卡頓。
 */
import { Virtuoso } from 'react-virtuoso';
import type { SeatIOFeedRow, SeatIOKind } from '../../types';
import { fmtUsd, fmtWhen } from '../../lib/agentUi';
import {
  SEAT_KIND_LABELS,
  attemptTag,
  fmtChars,
  fmtDuration,
  seatKindLabel,
  seatKindTone,
} from './seatModel';

const KIND_ORDER: SeatIOKind[] = Object.keys(SEAT_KIND_LABELS);

function FeedRow({
  row,
  selected,
  onPick,
}: {
  row: SeatIOFeedRow;
  selected: boolean;
  onPick: (row: SeatIOFeedRow) => void;
}) {
  const tone = seatKindTone(row.kind);
  const retry = attemptTag(row);
  const alert = row.degraded || Boolean(row.error);
  const preview = (row.prompt_preview || row.response_preview || '').split('\n')[0]?.trim() || '';
  return (
    <button
      type="button"
      onClick={() => onPick(row)}
      className={`block w-full border-b border-[var(--apple-hairline)] px-2.5 py-1.5 text-left transition-colors ${
        selected ? 'bg-[var(--apple-blue)]/12' : 'hover:bg-[var(--apple-surface)]'
      }`}
      style={selected ? { boxShadow: 'inset 2px 0 0 var(--apple-blue)' } : undefined}
    >
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="shrink-0 font-mono text-[9.5px] text-[var(--apple-tertiary)]">
          {fmtWhen(row.ts)}
        </span>
        <span
          className="shrink-0 rounded-[4px] px-1 py-[1px] text-[9.5px] font-medium"
          style={{ background: `${tone}22`, color: tone }}
        >
          {seatKindLabel(row.kind)}
        </span>
        <span className="shrink-0 font-mono text-[9.5px] text-[var(--apple-tertiary)]">
          {row.layer_label || `L${row.layer ?? '—'}`}
        </span>
        <span className="min-w-0 max-w-[9.5rem] truncate text-[11px] font-medium text-[var(--apple-label)]">
          {row.role_label || row.role}
        </span>
        {retry && (
          <span className="shrink-0 font-mono text-[9.5px] text-[var(--apple-orange)]">{retry}</span>
        )}
        {alert && (
          <span
            className="shrink-0 rounded-[4px] px-1 py-[1px] font-mono text-[9px]"
            style={{
              background: row.error ? 'rgba(255,69,58,.16)' : 'rgba(255,159,10,.16)',
              color: row.error ? 'var(--apple-red)' : 'var(--apple-orange)',
            }}
          >
            {row.error ? '錯誤' : '降級'}
          </span>
        )}
        <span className="ml-auto shrink-0 font-mono text-[9.5px] text-[var(--apple-secondary)]">
          {fmtDuration(row.duration_ms)}
        </span>
        <span className="shrink-0 font-mono text-[9.5px] text-[var(--apple-secondary)]">
          {row.cost_usd ? fmtUsd(row.cost_usd) : '$0'}
        </span>
      </div>
      <div className="mt-[2px] flex min-w-0 items-baseline gap-1.5">
        <span className="min-w-0 flex-1 truncate text-[11px] text-[var(--apple-label)]">
          {row.title || row.item_id || '（未命名投遞）'}
        </span>
        <span className="shrink-0 font-mono text-[9.5px] text-[var(--apple-tertiary)]">
          {fmtChars(row.prompt_length)}/{fmtChars(row.response_length)} 字
        </span>
      </div>
      <div className="mt-[1px] flex min-w-0 items-center gap-1.5 font-mono text-[9.5px] text-[var(--apple-tertiary)]">
        {row.model && <span className="shrink-0 truncate">{row.model}</span>}
        {preview && <span className="min-w-0 flex-1 truncate">{preview}</span>}
      </div>
    </button>
  );
}

export default function SeatFeedList({
  rows,
  kindCounts,
  kindFilter,
  roleFilter,
  selectedIoId,
  loading,
  error,
  source,
  polling,
  onKindFilter,
  onClearRole,
  onPick,
}: {
  rows: SeatIOFeedRow[];
  kindCounts: Record<string, number>;
  kindFilter: SeatIOKind | null;
  roleFilter: string | null;
  selectedIoId: string | null;
  loading: boolean;
  error: string | null;
  source: string;
  polling: boolean;
  onKindFilter: (kind: SeatIOKind | null) => void;
  onClearRole: () => void;
  onPick: (row: SeatIOFeedRow) => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-1 border-b border-[var(--apple-hairline)] px-2.5 py-1.5">
        <span className="mr-1 text-[10px] font-medium uppercase tracking-wide text-[var(--apple-tertiary)]">
          投遞流水
          <span className="ml-1 font-mono normal-case text-[var(--apple-secondary)]">{rows.length}</span>
        </span>
        {KIND_ORDER.filter((k) => kindCounts[String(k)]).map((k) => {
          const active = kindFilter === k;
          const tone = seatKindTone(String(k));
          return (
            <button
              key={String(k)}
              type="button"
              onClick={() => onKindFilter(active ? null : k)}
              className="rounded-[6px] border px-1.5 py-[2px] font-mono text-[9.5px] transition-colors"
              style={{
                borderColor: active ? tone : 'var(--apple-hairline)',
                background: active ? `${tone}22` : 'transparent',
                color: active ? tone : 'var(--apple-secondary)',
              }}
            >
              {seatKindLabel(String(k))} {kindCounts[String(k)]}
            </button>
          );
        })}
        {roleFilter && (
          <button
            type="button"
            onClick={onClearRole}
            className="ml-auto rounded-[6px] border border-[var(--apple-blue)]/50 bg-[var(--apple-blue)]/12 px-1.5 py-[2px] text-[9.5px] text-[var(--apple-label)]"
            title="清除席位過濾"
          >
            席位：{roleFilter} ✕
          </button>
        )}
        <span
          className={`ml-auto shrink-0 font-mono text-[9.5px] ${roleFilter ? '' : 'ml-auto'}`}
          style={{ color: polling ? 'var(--apple-green)' : 'var(--apple-tertiary)' }}
        >
          {polling ? '● 2.5s 輪詢中' : source === 'disk' ? '○ 歷史檔（不輪詢）' : '○ 已暫停'}
        </span>
      </div>

      {error && (
        <p className="shrink-0 border-b border-[var(--apple-hairline)] bg-[var(--apple-red)]/10 px-2.5 py-1.5 text-[10.5px]" style={{ color: 'var(--apple-red)' }}>
          {error}
        </p>
      )}

      {rows.length === 0 ? (
        <div className="flex min-h-0 flex-1 items-center justify-center px-6 py-8 text-center">
          {loading ? (
            <p className="text-[11.5px] text-[var(--apple-secondary)]">讀取投遞軌跡中…</p>
          ) : (
            <div>
              <p className="text-[12px] text-[var(--apple-label)]">
                {kindFilter || roleFilter ? '目前過濾條件下沒有投遞' : '尚無投遞軌跡'}
              </p>
              <p className="mt-1.5 text-[10.5px] leading-relaxed text-[var(--apple-secondary)]">
                {kindFilter || roleFilter
                  ? '改用上方標籤或左欄「全部席位」清除過濾。'
                  : '新任務尚未把任何 prompt 投遞給模型，或服務重啟後環形緩衝已清空且無持久檔。'}
              </p>
            </div>
          )}
        </div>
      ) : (
        <Virtuoso
          className="min-h-0 flex-1"
          data={rows}
          computeItemKey={(_i, row) => row.io_id || `${row.ts}-${row.role}-${row.kind}-${row.step}`}
          itemContent={(_i, row) => (
            <FeedRow row={row} selected={row.io_id === selectedIoId} onPick={onPick} />
          )}
        />
      )}
    </div>
  );
}
