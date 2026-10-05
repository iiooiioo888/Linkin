import './monitor.css';

export function MiniProgressBar({
  value,
  max = 100,
  hotThreshold = 85,
  hot: hotOverride,
  good,
}: {
  value: number;
  max?: number;
  hotThreshold?: number;
  /** 強制高負載色（優先於 hotThreshold） */
  hot?: boolean;
  good?: boolean;
}) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  const hot = hotOverride ?? pct >= hotThreshold;

  return (
    <div className="mon-mini-progress">
      <div className="mon-mini-progress__track">
        <div
          className={`mon-mini-progress__fill${hot ? ' mon-mini-progress__fill--hot' : good ? ' mon-mini-progress__fill--good' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="mon-mini-progress__val">{Math.round(pct)}%</span>
    </div>
  );
}
