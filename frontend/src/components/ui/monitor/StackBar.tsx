import type { StackSegment } from '../../../lib/monitorData';
import './monitor.css';

export function StackBar({ segments, showLegend = true }: { segments: StackSegment[]; showLegend?: boolean }) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;

  return (
    <div>
      <div className="mon-stack-bar" role="img" aria-label="狀態比例">
        {segments.map((seg) => (
          <div
            key={seg.label}
            className="mon-stack-bar__seg"
            style={{ width: `${(seg.value / total) * 100}%`, background: seg.color }}
            title={`${seg.label}: ${seg.value}`}
          />
        ))}
      </div>
      {showLegend ? (
        <div className="mt-1.5 flex flex-wrap gap-3">
          {segments.map((seg) => (
            <span key={seg.label} className="inline-flex items-center gap-1 text-[9px] text-[var(--console-faint)]">
              <span className="h-2 w-2 rounded-sm" style={{ background: seg.color }} />
              {seg.label} {seg.value}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
