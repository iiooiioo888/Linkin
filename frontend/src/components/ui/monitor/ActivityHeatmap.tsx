import type { HeatmapCell } from '../../../lib/monitorData';
import './monitor.css';

export function ActivityHeatmap({
  rows,
  rowLabels,
  title,
  demo,
}: {
  rows: HeatmapCell[][];
  rowLabels?: string[];
  title?: string;
  /** 標記為示範／空資料佔位 */
  demo?: boolean;
}) {
  const labels = rowLabels ?? ['一', '二', '三', '四', '五', '六', '日'];
  const empty = rows.every((r) => r.every((c) => c.level === 0 && !c.error));

  return (
    <div>
      {title ? (
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--console-faint)]">
          {title}
          {demo || empty ? <span className="ml-1 font-normal normal-case text-[var(--console-faint)]">（累積中）</span> : null}
        </p>
      ) : null}
      <div className="space-y-1">
        {rows.map((row, ri) => (
          <div key={ri}>
            <div className="mon-heatmap__label">{labels[ri] ?? `R${ri + 1}`}</div>
            <div className="mon-heatmap" role="img" aria-label={`活動熱力圖第 ${ri + 1} 行`}>
              {row.map((cell, ci) => (
                <div
                  key={ci}
                  className={`mon-heatmap__cell mon-heatmap__cell--l${cell.error ? 0 : cell.level}${cell.error ? ' mon-heatmap__cell--err' : ''}`}
                  title={`活動等級 ${cell.level}${cell.error ? ' · 錯誤' : ''}`}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
