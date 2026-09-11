import { matrixToneColor, type MatrixCell } from '../../../lib/monitorData';
import './monitor.css';

const ROW_LABELS = ['L4', 'L3', 'L2'];

const LEGEND: Array<{ tone: MatrixCell['tone']; label: string }> = [
  { tone: 'green', label: '完成' },
  { tone: 'blue', label: '執行' },
  { tone: 'gold', label: '當前時' },
  { tone: 'red', label: '失敗' },
  { tone: 'purple', label: '審計' },
];

export function TaskDistributionMatrix({
  matrix,
  demo,
}: {
  matrix: MatrixCell[][];
  demo?: boolean;
}) {
  const empty = matrix.every((row) => row.every((c) => c.count === 0));

  return (
    <div>
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--console-faint)]">
        任務分佈 · L4/L3/L2 × 24h
        {demo || empty ? <span className="ml-1 font-normal normal-case">（累積中）</span> : null}
      </p>
      <div className="mon-matrix-scroll">
        <div className="mon-matrix">
          {matrix.map((row, ri) => (
            <div key={ROW_LABELS[ri]} className="mon-matrix__row">
              <span className="mon-matrix__row-label">{ROW_LABELS[ri]}</span>
              {row.map((cell, ci) => (
                <div
                  key={ci}
                  className="mon-matrix__cell"
                  style={{
                    background: cell.count > 0
                      ? matrixToneColor(cell.tone)
                      : 'var(--console-dim)',
                    opacity: cell.count > 0 ? Math.min(1, 0.4 + cell.count * 0.15) : 1,
                  }}
                  title={`${ROW_LABELS[ri]} ${ci}:00 — ${cell.count} 任務`}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="mon-matrix__legend">
        {LEGEND.map((l) => (
          <span key={l.tone} className="mon-matrix__legend-item">
            <span className="mon-matrix__legend-dot" style={{ background: matrixToneColor(l.tone) }} />
            {l.label}
          </span>
        ))}
      </div>
    </div>
  );
}
